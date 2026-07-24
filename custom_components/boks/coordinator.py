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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

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
    KEEPALIVE_INTERVAL,
    NOTIFY_UUID,
    OPCODE_ANSWER_DOOR_STATUS,
    OPCODE_INVALID_OPEN_CODE,
    OPCODE_NOTIFY_DOOR_STATUS,
    OPCODE_VALID_OPEN_CODE,
    OPEN_TIMEOUT,
    RECONNECT_DELAY_MAX,
    RECONNECT_DELAY_MIN,
    SOFTWARE_UUID,
    WRITE_UUID,
)
from .protocol import (
    ASK_DOOR_STATUS_FRAME,
    build_open_door_frame,
    door_is_open,
    parse_frame,
)

_LOGGER = logging.getLogger(__name__)


class BoksOpenError(HomeAssistantError):
    """L'ouverture n'a pas abouti — code refusé, hors de portée, ou silence."""


@dataclass
class BoksState:
    """État courant publié aux entités."""

    connected: bool = False
    door_open: bool | None = None
    battery: int | None = None
    rssi: int | None = None
    firmware: str | None = None
    software: str | None = None
    #: Renseigné une fois la première lecture faite (nom d'appareil lisible).
    name: str | None = None
    #: Dernière fois que le lien GATT a été établi. Sert de diagnostic et dit
    #: depuis quand les valeurs affichées datent quand le lien est coupé.
    last_connected: datetime | None = None
    #: Plus haut niveau observé depuis la mise en place du jeu de piles courant.
    #: Sert de référence en mode régulé, où seul le décrochage est lisible.
    battery_plateau: int | None = None


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
        #: Résultat attendu d'un OPEN_DOOR en cours (129/130).
        self._open_result: asyncio.Future[bool] | None = None
        #: Sérialise les ouvertures : deux commandes concurrentes se
        #: voleraient mutuellement la réponse.
        self._open_lock = asyncio.Lock()
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
        #: Baisse franche en attente de confirmation (cf. BATTERY_TRANSIENT_DROP).
        self._battery_candidate: int | None = None

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
        remontée est toujours retenue immédiatement ; une chute franche ne l'est
        qu'après confirmation par une seconde lecture identique.
        """
        current = self.state.battery
        if current is not None and level <= current - BATTERY_TRANSIENT_DROP:
            if self._battery_candidate != level:
                self._battery_candidate = level
                _LOGGER.debug(
                    "creux batterie %s%% ignoré (courant %s%%), en attente de confirmation",
                    level,
                    current,
                )
                return False
        self._battery_candidate = None
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
        self.state.name = device.name or self.address
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

            while not self._stop.is_set() and client.is_connected:
                # Réarme le watchdog de la Boks et rafraîchit l'état de la porte.
                await client.write_gatt_char(
                    WRITE_UUID, ASK_DOOR_STATUS_FRAME, response=True
                )
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
