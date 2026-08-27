"""Liaison BLE persistante avec la Boks.

Mode push : la connexion est maintenue en permanence et la Boks pousse ses
changements d'état (porte, batterie) par notification GATT. Aucun polling
n'est effectué — seul un keepalive périodique est nécessaire pour empêcher
la Boks de fermer la connexion (watchdog applicatif ~30 s).

Le passage par la stack Bluetooth de Home Assistant permet d'atteindre la
Boks à travers n'importe quel proxy Bluetooth ESPHome déclaré (c'est ainsi
que le lien radio est établi ici).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    BATTERY_LOW_ALKALINE,
    BATTERY_SAG_REGULATED,
    BATTERY_TRANSIENT_DROP,
    BATTERY_UUID,
    FIRMWARE_UUID,
    HISTORY_EVENT_OPCODES,
    KEEPALIVE_INTERVAL,
    ADMIN_ACK_TIMEOUT,
    NFC_CONFIG_TYPE_LAPOSTE,
    NFC_RESPONSE_OPCODES,
    NFC_SCAN_TIMEOUT,
    NOTIFY_UUID,
    OPCODE_ANSWER_DOOR_STATUS,
    OPCODE_ERROR_NFC_SCAN_TIMEOUT,
    OPCODE_ERROR_NFC_TAG_ALREADY_EXISTS_SCAN,
    OPCODE_ERROR_UNAUTHORIZED,
    OPCODE_INVALID_OPEN_CODE,
    OPCODE_LOG_END_HISTORY,
    OPCODE_NOTIFY_DOOR_STATUS,
    OPCODE_NOTIFY_NFC_TAG_FOUND,
    OPCODE_NOTIFY_NFC_TAG_REGISTERED,
    OPCODE_NOTIFY_NFC_TAG_REGISTERED_ERROR_ALREADY_EXISTS,
    OPCODE_NOTIFY_NFC_TAG_UNREGISTERED,
    OPCODE_VALID_OPEN_CODE,
    OPEN_TIMEOUT,
    RECONNECT_DELAY_MAX,
    RECONNECT_DELAY_MIN,
    REBOOT_DEBOUNCE,
    SOFTWARE_UUID,
    WRITE_UUID,
)
from .protocol import (
    ASK_DOOR_STATUS_FRAME,
    GET_LOGS_COUNT_FRAME,
    REBOOT_FRAME,
    REQUEST_LOGS_FRAME,
    build_open_door_frame,
    build_register_nfc_frame,
    build_scan_start_frame,
    build_set_configuration_frame,
    build_unregister_nfc_frame,
    door_is_open,
    history_opening,
    parse_frame,
    parse_uid,
)

_LOGGER = logging.getLogger(__name__)


class BoksOpenError(HomeAssistantError):
    """L'ouverture n'a pas abouti — code refusé, hors de portée, ou silence."""


class BoksAdminError(HomeAssistantError):
    """Une opération d'administration (NFC/VIGIK) a échoué — voir le message."""


class BoksRebootError(HomeAssistantError):
    """Le redémarrage n'a pas pu être envoyé — voir le message."""


@dataclass
class BoksState:
    """État courant publié aux entités."""

    connected: bool = False
    door_open: bool | None = None
    battery: int | None = None
    rssi: int | None = None
    firmware: str | None = None
    software: str | None = None
    #: Dernière fois que le lien GATT a été établi. Sert de diagnostic et dit
    #: depuis quand les valeurs affichées datent quand le lien est coupé.
    last_connected: datetime | None = None
    #: Plus haut niveau observé depuis la mise en place du jeu de piles courant.
    #: Sert de référence en mode régulé, où seul le décrochage est lisible.
    battery_plateau: int | None = None
    #: Dérivées de l'historique de la boîte (âge relatif → date). Approximatives
    #: (la boîte n'a pas d'horloge) et rafraîchies à chaque lecture d'historique.
    last_vigik_open: datetime | None = None
    last_mifare_open: datetime | None = None
    last_code_open: datetime | None = None


#: Catégorie d'ouverture (cf. protocol.history_opening) → attribut de BoksState.
_OPENING_ATTR: dict[str, str] = {
    "vigik": "last_vigik_open",
    "mifare": "last_mifare_open",
    "code": "last_code_open",
}


class BoksLink:
    """Maintient la connexion à la Boks et diffuse son état."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        keepalive: float = KEEPALIVE_INTERVAL,
        reconnect_max: float = RECONNECT_DELAY_MAX,
        open_code: str | None = None,
        label: str | None = None,
        refresh_interval: int = 0,
        config_key: str | None = None,
    ) -> None:
        self.hass = hass
        self.address = address
        #: Période de réarmement du watchdog de la Boks. Réglable depuis les
        #: options : c'est le principal levier sur la consommation quand le
        #: lien est maintenu.
        self.keepalive = keepalive
        #: Plafond du backoff de reconnexion.
        self.reconnect_max = reconnect_max
        #: Code d'ouverture. Absent = pas de bouton d'ouverture, l'intégration
        #: reste strictement en lecture.
        self.open_code = open_code
        #: Identifiant lisible saisi par l'utilisateur (ex. « F540 »). Sert à
        #: nommer l'appareil : sans lui, deux boîtes s'appelleraient « Boks ».
        self.label = label
        #: Config Key du propriétaire (8 hex). Absente = pas de capacité d'admin
        #: NFC/VIGIK exposée, et le lien reste incapable de ces écritures.
        self.config_key = config_key
        #: Résultat attendu d'un OPEN_DOOR en cours (129/130).
        self._open_result: asyncio.Future[bool] | None = None
        #: Réponse NFC/admin en attente (opcode, payload) — cf. NFC_RESPONSE_OPCODES.
        self._nfc_result: asyncio.Future[tuple[int, bytes]] | None = None
        #: Sérialise les ouvertures : deux commandes concurrentes se
        #: voleraient mutuellement la réponse.
        self._open_lock = asyncio.Lock()
        #: Sérialise les opérations d'admin (une seule à la fois).
        self._admin_lock = asyncio.Lock()
        #: Horodatage (loop.time()) du dernier reboot envoyé — anti-rebond,
        #: voir async_reboot / const.REBOOT_DEBOUNCE.
        self._last_reboot: float | None = None
        #: UID saisi dans l'entité texte, consommé par le bouton « Révoquer ».
        self.pending_unregister_uid: str = ""
        self.state = BoksState()
        self._client: BleakClientWithServiceCache | None = None
        self._listeners: list[Callable[[], None]] = []
        self._runner: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._unregister_adv: Callable[[], None] | None = None
        #: Faut-il maintenir le lien GATT ? Piloté par le switch « connexion
        #: maintenue ». Tant qu'il est faux, on se contente d'écouter les
        #: advertisements — ce qui ne coûte rien à la Boks, là où un lien tenu
        #: garde sa radio éveillée en permanence et vide ses piles.
        self._hold = False
        #: Le jeu de piles en place est-il à tension régulée (lithium 1,5 V
        #: rechargeable) ? Piloté par le switch « piles rechargeables ».
        self._rechargeable = False
        #: Une chute franche est-elle en attente de confirmation par la lecture
        #: suivante ? (cf. BATTERY_TRANSIENT_DROP et _accept_battery.)
        self._battery_sagging = False
        #: Intervalle (minutes) du rafraîchissement périodique ; 0 = désactivé.
        self.refresh_interval = refresh_interval
        self._refresh_runner: asyncio.Task | None = None
        self._stop_refresh = asyncio.Event()
        #: Collecteur d'événements pendant une lecture d'historique (None sinon).
        self._history: list[tuple[int, bytes]] | None = None
        self._history_done: asyncio.Event | None = None

    @property
    def hold(self) -> bool:
        """Vrai si le lien GATT doit être maintenu."""
        return self._hold

    @property
    def rechargeable(self) -> bool:
        """Vrai si le pack en place est à tension régulée."""
        return self._rechargeable

    @callback
    def async_set_rechargeable(self, rechargeable: bool) -> None:
        """Déclare le type de piles en place.

        Le basculement vaut « nouveau jeu de piles » : le plateau de référence
        est remis à zéro, sans quoi on comparerait le pack neuf au maximum
        observé sur le précédent.
        """
        if rechargeable == self._rechargeable:
            return
        self._rechargeable = rechargeable
        self.state.battery_plateau = self.state.battery
        self._notify_listeners()

    @property
    def battery_low(self) -> bool | None:
        """Le jeu de piles est-il en fin de vie ?

        Deux régimes, parce que la grandeur mesurée n'a pas le même sens :

        - **Alcalines** — la tension décroît régulièrement, le pourcentage
          publié par la Boks est exploitable tel quel : seuil classique.
        - **Lithium régulées** — la tension reste plate jusqu'à la coupure de
          la protection. Le niveau ne renseigne plus sur la charge restante,
          seulement sur le fait que le pack commence à ne plus tenir. Tout
          décrochage durable sous le plateau est donc déjà une alerte.
        """
        level = self.state.battery
        if level is None:
            return None
        if not self._rechargeable:
            return level <= BATTERY_LOW_ALKALINE
        plateau = self.state.battery_plateau
        if plateau is None:
            return None
        return level <= plateau - BATTERY_SAG_REGULATED

    def _accept_battery(self, level: int) -> bool:
        """Écarte les creux de tension passagers.

        L'ouverture de la porte sollicite le moteur : la tension plonge le temps
        de la manœuvre et la Boks a déjà publié 0 % dans ces conditions. Une
        chute franche est donc mise en attente une lecture ; elle n'est retenue
        que si la lecture suivante reste basse, confirmant une baisse réelle et
        non un creux d'une seule mesure.

        Point important : la confirmation ne porte **pas** sur une valeur
        identique. Une décharge réelle — surtout l'effondrement brutal des
        lithium régulées — enchaîne des valeurs différentes (p. ex. 100 → 40 →
        10). Exiger deux lectures égales laisserait alors le capteur bloqué en
        haut d'échelle pendant que les piles meurent. On confirme donc « encore
        bas », pas « le même chiffre ».
        """
        current = self.state.battery
        is_sharp_drop = (
            current is not None and level <= current - BATTERY_TRANSIENT_DROP
        )
        if is_sharp_drop and not self._battery_sagging:
            # Première lecture basse : peut n'être qu'un creux moteur. On la met
            # en attente sans la retenir (la valeur courante ne bouge pas).
            self._battery_sagging = True
            _LOGGER.debug(
                "creux batterie %s%% ignoré (courant %s%%), en attente de confirmation",
                level,
                current,
            )
            return False
        # Soit ce n'est pas une chute franche (remontée ou stabilité), soit
        # c'est une seconde lecture basse consécutive : baisse confirmée.
        self._battery_sagging = False
        return True

    @callback
    def _set_battery(self, level: int) -> None:
        """Retient un niveau de batterie et tient le plateau à jour."""
        if not self._accept_battery(level):
            return
        plateau = self.state.battery_plateau
        if plateau is None or level > plateau:
            self.state.battery_plateau = level
        if level != self.state.battery:
            self.state.battery = level
            self._notify_listeners()

    # ------------------------------------------------------------------ API
    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        """Abonne une entité aux changements d'état."""
        self._listeners.append(update)

        def _remove() -> None:
            if update in self._listeners:
                self._listeners.remove(update)

        return _remove

    @callback
    def _notify_listeners(self) -> None:
        for update in list(self._listeners):
            update()

    async def async_start(self) -> None:
        """Démarre l'écoute passive des advertisements.

        Le lien GATT, lui, n'est établi que si `async_set_hold(True)` est
        demandé — voir le switch « connexion maintenue ».
        """
        self._unregister_adv = bluetooth.async_register_callback(
            self.hass,
            self._async_on_advertisement,
            {"address": self.address, "connectable": False},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
        if self.refresh_interval > 0:
            self._stop_refresh.clear()
            self._refresh_runner = self.hass.async_create_background_task(
                self._async_refresh_loop(), name=f"boks-refresh[{self.address}]"
            )

    async def _async_refresh_loop(self) -> None:
        """Rafraîchissement périodique : connexion brève lien coupé.

        Toutes les ``refresh_interval`` minutes, si le lien n'est pas déjà
        maintenu, établit une session courte pour relire état, batterie et
        historique, puis se déconnecte. C'est le compromis « status et dates
        récents sans tenir le lien » — désactivé quand l'intervalle est 0.
        """
        while not self._stop_refresh.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_refresh.wait(), timeout=self.refresh_interval * 60
                )
                return  # arrêt demandé
            except TimeoutError:
                pass
            if self._hold:
                continue  # le lien maintenu rafraîchit déjà
            try:
                await self._async_refresh_once()
            except Exception as err:  # noqa: BLE001 - opportuniste, on réessaiera
                _LOGGER.debug("rafraîchissement périodique échoué: %s", err)

    async def _async_refresh_once(self) -> None:
        """Session courte de lecture : état + batterie + porte + historique."""
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            return
        client: BleakClientWithServiceCache = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self.address,
            self._on_disconnected,
            use_services_cache=False,
        )
        self.state.last_connected = datetime.now(timezone.utc)
        self._notify_listeners()
        try:
            await self._async_read_static(client)
            await client.start_notify(NOTIFY_UUID, self._on_app_notify)
            # Un ASK_DOOR_STATUS pour rafraîchir la porte, puis l'historique.
            await client.write_gatt_char(WRITE_UUID, ASK_DOOR_STATUS_FRAME, response=True)
            await asyncio.sleep(1)
            await self._async_read_history(client)
        finally:
            try:
                await client.clear_cache()
            except Exception as err:  # noqa: BLE001 - purement opportuniste
                _LOGGER.debug("purge du cache GATT impossible: %s", err)
            try:
                await client.disconnect()
            except (BleakError, EOFError) as err:
                _LOGGER.debug("déconnexion après rafraîchissement: %s", err)

    async def async_set_hold(self, hold: bool) -> None:
        """Établit ou libère le lien GATT permanent."""
        if hold == self._hold:
            return
        self._hold = hold
        if hold:
            self._stop.clear()
            self._runner = self.hass.async_create_background_task(
                self._async_run(), name=f"boks[{self.address}]"
            )
        else:
            await self._async_cancel_runner()
            await self._async_disconnect()
        self._notify_listeners()

    async def async_open_door(self) -> None:
        """Ouvre la porte.

        Fonctionne dans les deux régimes, ce qui est le point important : si le
        lien n'est pas maintenu, une session temporaire est établie le temps de
        la commande puis relâchée. Un bouton qui n'ouvrirait qu'avec le lien
        déjà tenu serait inutilisable en pratique, puisque le défaut — et le
        réglage économe — est justement de ne pas le tenir.

        Lève ``BoksOpenError`` si le code est refusé ou si la boîte ne répond
        pas : la réponse ``VALID_OPEN_CODE`` est la seule preuve d'ouverture,
        l'écriture GATT ne prouve rien à elle seule.
        """
        if not self.open_code:
            raise BoksOpenError("aucun code d'ouverture n'est configuré")
        frame = build_open_door_frame(self.open_code)

        async with self._open_lock:
            loop = asyncio.get_running_loop()
            self._open_result = loop.create_future()
            try:
                if self._client is not None and self._client.is_connected:
                    await self._client.write_gatt_char(WRITE_UUID, frame, response=True)
                else:
                    await self._async_open_via_temp_session(frame)
                accepted = await asyncio.wait_for(self._open_result, OPEN_TIMEOUT)
            except TimeoutError as err:
                raise BoksOpenError(
                    "la boîte n'a pas répondu — un code au mauvais format est "
                    "ignoré sans réponse, et la boîte peut être hors de portée"
                ) from err
            except (BleakError, EOFError) as err:
                raise BoksOpenError(f"échec de la liaison: {err}") from err
            finally:
                self._open_result = None

        if not accepted:
            raise BoksOpenError("code d'ouverture refusé par la boîte")
        _LOGGER.info("ouverture acceptée par %s", self.address)

    async def _async_open_via_temp_session(self, frame: bytes) -> None:
        """Établit une connexion le temps d'une commande, puis la relâche.

        On souscrit aux notifications avant d'écrire : sans CCCD, la réponse
        129/130 ne remonterait jamais et l'ouverture paraîtrait avoir échoué
        alors qu'elle a eu lieu.
        """
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise BoksOpenError(
                f"{self.address} hors de portée d'un adaptateur/proxy connectable"
            )

        client: BleakClientWithServiceCache = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self.address,
            self._on_disconnected,
            use_services_cache=False,
        )
        self.state.last_connected = datetime.now(timezone.utc)
        # Une connexion vient d'avoir lieu : le diagnostic de fraîcheur doit le
        # refléter, même brève et hors du lien maintenu. Sans cela, « Dernière
        # connexion » resterait indisponible après une ouverture réussie.
        self._notify_listeners()
        try:
            await client.start_notify(NOTIFY_UUID, self._on_app_notify)
            await client.write_gatt_char(WRITE_UUID, frame, response=True)
            # On attend la réponse ici, connexion encore ouverte : la relâcher
            # tout de suite couperait la notification qu'on cherche.
            if self._open_result is not None:
                await asyncio.wait_for(
                    asyncio.shield(self._open_result), OPEN_TIMEOUT
                )
        finally:
            try:
                await client.clear_cache()
            except Exception as err:  # noqa: BLE001 - purement opportuniste
                _LOGGER.debug("purge du cache GATT impossible: %s", err)
            try:
                await client.disconnect()
            except (BleakError, EOFError) as err:
                _LOGGER.debug("déconnexion après ouverture: %s", err)

    # --- Administration NFC / VIGIK (authentifié par Config Key) -----------

    async def _async_admin_write(
        self, client: BleakClientWithServiceCache, frame: bytes, timeout: float
    ) -> tuple[int, bytes]:
        """Écrit une trame d'admin et attend la réponse de la boîte.

        La réponse (197-202/225) remonte par ``_on_app_notify`` dans
        ``self._nfc_result``.
        """
        self._nfc_result = asyncio.get_running_loop().create_future()
        await client.write_gatt_char(WRITE_UUID, frame, response=True)
        return await asyncio.wait_for(asyncio.shield(self._nfc_result), timeout)

    async def _async_admin_session(
        self, body: Callable[[BleakClientWithServiceCache], Awaitable[None]]
    ) -> None:
        """Exécute ``body(client)`` sur une connexion, notifications souscrites.

        Réutilise le lien maintenu s'il existe ; sinon ouvre une session
        temporaire et la relâche après (comme pour l'ouverture).
        """
        if self._client is not None and self._client.is_connected:
            await body(self._client)
            return
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise BoksAdminError(
                f"{self.address} hors de portée d'un adaptateur/proxy connectable"
            )
        client: BleakClientWithServiceCache = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self.address,
            self._on_disconnected,
            use_services_cache=False,
        )
        self.state.last_connected = datetime.now(timezone.utc)
        self._notify_listeners()
        try:
            await client.start_notify(NOTIFY_UUID, self._on_app_notify)
            await body(client)
        finally:
            try:
                await client.clear_cache()
            except Exception as err:  # noqa: BLE001 - purement opportuniste
                _LOGGER.debug("purge du cache GATT impossible: %s", err)
            try:
                await client.disconnect()
            except (BleakError, EOFError) as err:
                _LOGGER.debug("déconnexion après admin: %s", err)

    @staticmethod
    def _found_uid(payload: bytes) -> bytes:
        """UID d'un ``NOTIFY_NFC_TAG_FOUND`` (197) : ``[uidLen][uid…]``."""
        if not payload:
            raise BoksAdminError("réponse de scan sans UID")
        n = payload[0]
        uid = payload[1 : 1 + n]
        if n == 0 or len(uid) != n:
            raise BoksAdminError("UID de badge incomplet dans la réponse")
        return bytes(uid)

    async def async_reboot(self) -> None:
        """Redémarre la carte de la Boks (opcode 6, sans payload).

        Contrairement à ``OPEN_DOOR``, aucune réponse applicative n'est
        attendue : la boîte coupe simplement le lien en redémarrant. Le
        succès de l'écriture GATT (``response=True``, donc acquittée au
        niveau ATT) est la seule confirmation disponible.

        Réutilise ``_async_admin_session`` : fonctionne que le lien soit
        maintenu ou non, comme l'ouverture et les opérations NFC — une
        session temporaire est établie si nécessaire puis relâchée.

        Anti-rebond de ``REBOOT_DEBOUNCE`` (60 s) : le redémarrage matériel
        prend au moins ~40 s, un second appui avant ce délai n'aurait
        pratiquement aucune chance d'aboutir et ne ferait qu'ajouter du bruit
        sur un lien déjà en train de tomber. Lève ``BoksRebootError`` plutôt
        que d'envoyer une seconde trame inutile.
        """
        now = asyncio.get_running_loop().time()
        if self._last_reboot is not None:
            elapsed = now - self._last_reboot
            if elapsed < REBOOT_DEBOUNCE:
                raise BoksRebootError(
                    "redémarrage déjà demandé récemment — réessayez dans "
                    f"{REBOOT_DEBOUNCE - elapsed:.0f} s"
                )
        self._last_reboot = now

        async def body(client: BleakClientWithServiceCache) -> None:
            await client.write_gatt_char(WRITE_UUID, REBOOT_FRAME, response=True)

        try:
            await self._async_admin_session(body)
        except (BleakError, EOFError) as err:
            raise BoksRebootError(f"échec de la liaison: {err}") from err
        _LOGGER.info("redémarrage envoyé à %s", self.address)

    async def async_register_nfc_tag(self) -> dict[str, str]:
        """Enrôle un badge : ``SCAN_START`` → présentation → ``REGISTER``.

        Renvoie ``{'uid': '<hex>', 'status': 'registered'|'already'}``. Lève
        ``BoksAdminError`` (affichée à l'utilisateur) sur refus, timeout ou
        absence de badge.
        """
        if not self.config_key:
            raise BoksAdminError("aucune Config Key n'est configurée")
        outcome: dict[str, str] = {}

        async def body(client: BleakClientWithServiceCache) -> None:
            opcode, payload = await self._async_admin_write(
                client, build_scan_start_frame(self.config_key), NFC_SCAN_TIMEOUT
            )
            if opcode == OPCODE_ERROR_UNAUTHORIZED:
                raise BoksAdminError("Config Key refusée par la boîte (225)")
            if opcode == OPCODE_ERROR_NFC_SCAN_TIMEOUT:
                raise BoksAdminError(
                    "aucun badge présenté à temps — appuyez sur une touche du "
                    "clavier puis présentez le badge"
                )
            if opcode == OPCODE_ERROR_NFC_TAG_ALREADY_EXISTS_SCAN:
                raise BoksAdminError("ce badge est déjà enregistré")
            if opcode != OPCODE_NOTIFY_NFC_TAG_FOUND:
                raise BoksAdminError(f"réponse inattendue au scan (opcode {opcode})")
            uid = self._found_uid(payload)
            outcome["uid"] = uid.hex().upper()
            op2, _ = await self._async_admin_write(
                client, build_register_nfc_frame(self.config_key, uid), ADMIN_ACK_TIMEOUT
            )
            if op2 == OPCODE_NOTIFY_NFC_TAG_REGISTERED:
                outcome["status"] = "registered"
            elif op2 == OPCODE_NOTIFY_NFC_TAG_REGISTERED_ERROR_ALREADY_EXISTS:
                outcome["status"] = "already"
            elif op2 == OPCODE_ERROR_UNAUTHORIZED:
                raise BoksAdminError("Config Key refusée par la boîte (225)")
            else:
                raise BoksAdminError(f"échec de l'enregistrement (opcode {op2})")

        async with self._admin_lock:
            try:
                await self._async_admin_session(body)
            except (BleakError, EOFError) as err:
                raise BoksAdminError(f"échec de la liaison: {err}") from err
            except TimeoutError as err:
                raise BoksAdminError("la boîte n'a pas répondu à temps") from err
            finally:
                self._nfc_result = None
        _LOGGER.info(
            "badge %s %s sur %s", outcome.get("uid"), outcome.get("status"), self.address
        )
        return outcome

    async def async_unregister_nfc_tag(self, uid_hex: str) -> None:
        """Révoque un badge par son UID hexadécimal."""
        if not self.config_key:
            raise BoksAdminError("aucune Config Key n'est configurée")
        try:
            uid = parse_uid(uid_hex)
        except ValueError as err:
            raise BoksAdminError(str(err)) from err

        async def body(client: BleakClientWithServiceCache) -> None:
            opcode, _ = await self._async_admin_write(
                client, build_unregister_nfc_frame(self.config_key, uid), ADMIN_ACK_TIMEOUT
            )
            if opcode == OPCODE_NOTIFY_NFC_TAG_UNREGISTERED:
                return
            if opcode == OPCODE_ERROR_UNAUTHORIZED:
                raise BoksAdminError("Config Key refusée par la boîte (225)")
            raise BoksAdminError(f"échec de la révocation (opcode {opcode})")

        async with self._admin_lock:
            try:
                await self._async_admin_session(body)
            except (BleakError, EOFError) as err:
                raise BoksAdminError(f"échec de la liaison: {err}") from err
            except TimeoutError as err:
                raise BoksAdminError("la boîte n'a pas répondu à temps") from err
            finally:
                self._nfc_result = None
        _LOGGER.info("badge %s révoqué sur %s", uid.hex().upper(), self.address)

    async def async_set_vigik(self, enabled: bool) -> None:
        """Active/désactive le VIGIK (``SET_CONFIGURATION`` type LaPosteNfc).

        Un refus d'auth remonte en ``225``. L'accusé positif exact n'étant pas
        encore confirmé sur matériel, on ne fait PAS échouer sur un silence :
        seul un ``225`` est traité comme une erreur.
        """
        if not self.config_key:
            raise BoksAdminError("aucune Config Key n'est configurée")
        frame = build_set_configuration_frame(
            self.config_key, NFC_CONFIG_TYPE_LAPOSTE, enabled
        )

        async def body(client: BleakClientWithServiceCache) -> None:
            try:
                opcode, _ = await self._async_admin_write(client, frame, ADMIN_ACK_TIMEOUT)
            except TimeoutError:
                return  # pas d'accusé explicite connu → silence ≠ échec
            if opcode == OPCODE_ERROR_UNAUTHORIZED:
                raise BoksAdminError("Config Key refusée par la boîte (225)")

        async with self._admin_lock:
            try:
                await self._async_admin_session(body)
            except (BleakError, EOFError) as err:
                raise BoksAdminError(f"échec de la liaison: {err}") from err
            finally:
                self._nfc_result = None
        _LOGGER.info("VIGIK %s sur %s", "activé" if enabled else "désactivé", self.address)

    async def _async_cancel_runner(self) -> None:
        self._stop.set()
        if self._runner is not None:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
            self._runner = None

    async def async_stop(self) -> None:
        """Arrête proprement la liaison."""
        self._hold = False
        if self._unregister_adv is not None:
            self._unregister_adv()
            self._unregister_adv = None
        self._stop_refresh.set()
        if self._refresh_runner is not None:
            self._refresh_runner.cancel()
            try:
                await self._refresh_runner
            except asyncio.CancelledError:
                pass
            self._refresh_runner = None
        await self._async_cancel_runner()
        await self._async_disconnect()

    # -------------------------------------------------------------- interne
    @callback
    def _async_on_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Met à jour le RSSI depuis les advertisements (sans connexion)."""
        if service_info.rssi != self.state.rssi:
            self.state.rssi = service_info.rssi
            self._notify_listeners()

    async def _async_sleep(self, delay: float) -> None:
        """Attente interruptible par l'arrêt."""
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=delay)
        except TimeoutError:
            pass

    async def _async_run(self) -> None:
        """Boucle : connecte, maintient, reconnecte avec backoff."""
        delay = RECONNECT_DELAY_MIN
        while not self._stop.is_set():
            try:
                await self._async_session()
                delay = RECONNECT_DELAY_MIN
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - on relance quoi qu'il arrive
                _LOGGER.debug("session Boks terminée (%s) — nouvel essai", err)
            if self._stop.is_set():
                break
            self._set_disconnected()
            await self._async_sleep(delay)
            delay = min(delay * 2, self.reconnect_max)

    async def _async_session(self) -> None:
        """Une session complète : connexion, souscriptions, keepalive."""
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise BleakError(
                f"{self.address} hors de portée d'un adaptateur/proxy connectable"
            )

        client: BleakClientWithServiceCache = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self.address,
            self._on_disconnected,
            use_services_cache=False,
        )
        self._client = client
        self.state.connected = True
        self.state.last_connected = datetime.now(timezone.utc)
        _LOGGER.debug("connecté à %s", self.address)

        try:
            await self._async_read_static(client)
            # start_notify écrit le CCCD : c'est ce qui active réellement le push.
            await client.start_notify(NOTIFY_UUID, self._on_app_notify)
            try:
                await client.start_notify(BATTERY_UUID, self._on_battery_notify)
            except (BleakError, EOFError) as err:
                _LOGGER.debug("notify batterie indisponible: %s", err)
            self._notify_listeners()

            # Lecture d'historique — UNIQUEMENT si le suivi est activé
            # (refresh_interval > 0). REQUEST_LOGS *draine* le journal (curseur
            # persistant côté boîte) qui sert de backlog au BoksLINK officiel :
            # on ne draine donc jamais sans que l'utilisateur l'ait choisi.
            loop = asyncio.get_running_loop()
            next_history: float | None = None
            if self.refresh_interval > 0:
                try:
                    await self._async_read_history(client)
                except (BleakError, EOFError) as err:
                    _LOGGER.debug("lecture historique impossible: %s", err)
                next_history = loop.time() + self.refresh_interval * 60

            # Objectif : reproduire ce que fait le BoksLINK officiel — une
            # connexion tenue en continu, avec surveillance active — mais en
            # poussant vers Home Assistant plutôt que vers le cloud Boks. Porte
            # et batterie sont déjà en push (notifications) ; l'historique, lui,
            # n'est PAS poussé par la boîte et doit être re-demandé pour capter
            # les ouvertures survenues pendant que le lien reste ouvert — sinon
            # une session tenue des heures ne verrait plus jamais de nouvelle
            # date VIGIK/code après sa lecture initiale.
            while not self._stop.is_set() and client.is_connected:
                # Réarme le watchdog de la Boks et rafraîchit l'état de la porte.
                await client.write_gatt_char(
                    WRITE_UUID, ASK_DOOR_STATUS_FRAME, response=True
                )
                if next_history is not None and loop.time() >= next_history:
                    try:
                        await self._async_read_history(client)
                    except (BleakError, EOFError) as err:
                        _LOGGER.debug("re-lecture historique impossible: %s", err)
                    next_history = loop.time() + self.refresh_interval * 60
                await self._async_sleep(self.keepalive)
        finally:
            # Le cache GATT doit repartir vide à chaque session. Home Assistant
            # réutilise ses services en cache dès que le proxy annonce la
            # capacité REMOTE_CACHING (et ce, quel que soit `use_services_cache`,
            # cf. bleak_esphome : `REMOTE_CACHING or dangerous_use_bleak_cache`).
            # Or les proxys ESPHome ne résolvent les characteristics qu'après une
            # requête GetServices explicite : sans elle, le proxy n'a aucun objet
            # côté connexion et toutes les opérations échouent (error=-2). Vider
            # le cache ici force la découverte au prochain rattachement.
            try:
                await client.clear_cache()
            except Exception as err:  # noqa: BLE001 - purement opportuniste
                _LOGGER.debug("purge du cache GATT impossible: %s", err)
            await self._async_disconnect()

    async def _async_read_static(self, client: BleakClientWithServiceCache) -> None:
        """Lit les caractéristiques standard (non authentifiées)."""
        for uuid, attr, decoder in (
            (FIRMWARE_UUID, "firmware", lambda b: b.decode("utf-8", "replace").strip()),
            (SOFTWARE_UUID, "software", lambda b: b.decode("utf-8", "replace").strip()),
        ):
            try:
                raw = await client.read_gatt_char(uuid)
            except (BleakError, EOFError) as err:
                _LOGGER.debug("lecture %s impossible: %s", uuid, err)
                continue
            setattr(self.state, attr, decoder(bytes(raw)))

        # La batterie passe par le même filtre que les notifications : une
        # lecture faite juste après une ouverture de porte est tout aussi
        # susceptible d'attraper un creux de tension.
        try:
            raw = await client.read_gatt_char(BATTERY_UUID)
        except (BleakError, EOFError) as err:
            _LOGGER.debug("lecture batterie impossible: %s", err)
        else:
            if raw:
                self._set_battery(bytes(raw)[0])

    async def _async_read_history(
        self, client: BleakClientWithServiceCache
    ) -> None:
        """Draine le journal d'événements et en tire les dernières ouvertures.

        Non authentifié : ``GET_LOGS_COUNT`` puis ``REQUEST_LOGS`` (payloads
        vides). La boîte streame ses événements via les notifications (routées
        dans ``_on_app_notify``) jusqu'à ``LOG_END_HISTORY``.

        ⚠️ **Sémantique de drain.** ``REQUEST_LOGS`` **consomme** un curseur
        **persistant côté boîte** : chaque lecture ne renvoie que les événements
        **non encore lus**, puis les marque lus — une relecture ultérieure
        (même après reconnexion) renvoie donc *rien* tant qu'aucun nouvel
        événement n'est survenu. On **accumule** donc : chaque drain ne fait
        qu'**avancer** les dates VIGIK / code (jamais régresser), et la
        persistance (`RestoreEntity`) conserve le dernier connu.

        Les dates dérivent d'un âge relatif (la boîte n'a pas d'horloge), donc
        approximatives. Suppose les notifications déjà activées par l'appelant.
        """
        self._history = []
        self._history_done = asyncio.Event()
        loop = asyncio.get_running_loop()
        try:
            await client.write_gatt_char(WRITE_UUID, GET_LOGS_COUNT_FRAME, response=True)
            await asyncio.sleep(0.5)  # laisse arriver NOTIFY_LOGS_COUNT
            # REQUEST_LOGS fait avancer le curseur ; on relance tant que le flux
            # progresse. Borné par un plafond de temps ET un nombre de tours
            # « à vide » consécutifs — la latence via un proxy ESPHome dépasse
            # largement une seule fenêtre courte.
            deadline = loop.time() + 25.0
            idle = 0
            last = -1
            while loop.time() < deadline and not self._history_done.is_set():
                await client.write_gatt_char(
                    WRITE_UUID, REQUEST_LOGS_FRAME, response=True
                )
                try:
                    await asyncio.wait_for(self._history_done.wait(), timeout=2.0)
                except TimeoutError:
                    pass
                count = len(self._history)
                idle = idle + 1 if count == last else 0
                last = count
                if idle >= 3:
                    break  # trois tours sans nouvel événement
            events = self._history
        finally:
            self._history = None
            self._history_done = None
        _LOGGER.debug("historique: %d trames collectées (drain)", len(events))

        now = datetime.now(timezone.utc)
        latest: dict[str, int] = {}  # kind → plus petit âge vu (= plus récent)
        for opcode, payload in events:
            parsed = history_opening(opcode, payload)
            if parsed is None:
                continue
            kind, age = parsed
            if kind not in latest or age < latest[kind]:
                latest[kind] = age

        # Accumulation : on n'avance une date que si le drain apporte plus récent
        # (le drain ne peut donner que des événements postérieurs au dernier lu,
        # mais on reste robuste vis-à-vis de la valeur persistée).
        changed = False
        for kind, age in latest.items():
            attr = _OPENING_ATTR[kind]
            date = now - timedelta(seconds=age)
            if getattr(self.state, attr) is None or date > getattr(self.state, attr):
                setattr(self.state, attr, date)
                changed = True
        if changed:
            _LOGGER.debug(
                "historique: %d événements, VIGIK=%s Mifare=%s code=%s",
                len(events),
                self.state.last_vigik_open,
                self.state.last_mifare_open,
                self.state.last_code_open,
            )
            self._notify_listeners()

    @callback
    def _on_app_notify(self, _char: BleakGATTCharacteristic, data: bytearray) -> None:
        """Notification applicative : état de la porte poussé par la Boks."""
        parsed = parse_frame(bytes(data))
        if parsed is None:
            return
        opcode, payload = parsed
        if opcode in (OPCODE_VALID_OPEN_CODE, OPCODE_INVALID_OPEN_CODE):
            if self._open_result is not None and not self._open_result.done():
                self._open_result.set_result(opcode == OPCODE_VALID_OPEN_CODE)
            return
        # Réponses aux opérations d'admin NFC/VIGIK → Future en attente.
        if opcode in NFC_RESPONSE_OPCODES:
            if self._nfc_result is not None and not self._nfc_result.done():
                self._nfc_result.set_result((opcode, payload))
            return
        # Pendant une lecture d'historique, la boîte streame ses événements ici.
        if self._history is not None and opcode in HISTORY_EVENT_OPCODES:
            self._history.append((opcode, payload))
            if opcode == OPCODE_LOG_END_HISTORY and self._history_done is not None:
                self._history_done.set()
            return
        if opcode not in (OPCODE_NOTIFY_DOOR_STATUS, OPCODE_ANSWER_DOOR_STATUS):
            _LOGGER.debug("opcode %s ignoré (%s)", opcode, bytes(data).hex())
            return
        is_open = door_is_open(payload)
        if is_open is None or is_open == self.state.door_open:
            return
        self.state.door_open = is_open
        _LOGGER.debug("porte %s", "ouverte" if is_open else "fermée")
        self._notify_listeners()

    @callback
    def _on_battery_notify(
        self, _char: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Notification batterie standard (0x2A19) : un octet de pourcentage."""
        if not data:
            return
        self._set_battery(data[0])

    @callback
    def _on_disconnected(self, _client: BleakClientWithServiceCache) -> None:
        _LOGGER.debug("déconnecté de %s", self.address)
        self._set_disconnected()

    @callback
    def _set_disconnected(self) -> None:
        if self.state.connected:
            self.state.connected = False
            self._notify_listeners()

    async def _async_disconnect(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await client.disconnect()
        except (BleakError, EOFError, asyncio.TimeoutError) as err:
            _LOGGER.debug("déconnexion imparfaite: %s", err)
        self._set_disconnected()
