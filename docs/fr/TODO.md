> 🇬🇧 **[English version](../../TODO.md)**

# Feuille de route / sujets ouverts

Sujets encore à traiter. Ce sont des directions, pas des engagements ni des
dates. Les contributions sont bienvenues — une pull request ciblée par sujet.

Règle directrice : l'intégration reste **en lecture seule par défaut**. Toute
fonction émettant plus qu'une requête de statut ou qu'une commande d'ouverture
volontaire doit rester derrière une configuration explicite de l'utilisateur, et
ne jamais élargir en silence la liste blanche des opcodes émis.

---

## 1. Badge NFC Mifare

**Objectif.** Lire, enregistrer et révoquer depuis Home Assistant les badges NFC
Mifare servant à ouvrir la boîte.

**Ce que l'on sait.** Le protocole Boks réserve des opcodes pour exactement
cela — `REGISTER_NFC_TAG_SCAN_START` (23), `REGISTER_NFC_TAG` (24),
`UNREGISTER_NFC_TAG` (25) — avec les notifications correspondantes
(`NOTIFY_NFC_TAG_FOUND`, `NOTIFY_NFC_TAG_REGISTERED`, …). Le SDK constructeur
expose `scanNFCTags()`, `registerNfcTag()`, `unregisterNfcTag()`.

**Ce qu'il faut.** Ce sont des opérations administratives : elles exigent la
**Config Key** du propriétaire (récupérable via l'API du compte) et écrivent
dans la boîte. Les implémenter suppose d'ajouter ces opcodes à la liste blanche
*uniquement lorsqu'une Config Key est configurée*, sur le modèle de l'ouverture
à distance déjà conditionnée à un code.

**Matériel.** Le NFC est **confirmé fonctionnel sur la boîte de référence** —
six badges Mifare y sont activement utilisés — alors même qu'elle renvoie
`Model Number = 2.0` et n'expose aucune characteristic Hardware Revision. La
mention « HW ≥ 4.0 » du SDK ne l'empêche donc pas ici, et la fonction peut être
développée et testée sur du vrai matériel. D'autres générations peuvent
néanmoins différer : la fonction devra détecter la capacité plutôt que la
supposer.

**État.** Non commencé. Document de conception d'abord (gestion du secret, échec
à mi-parcours, détection de capacité), comme convenu pour toute fonction
d'écriture. Testable de bout en bout sur la boîte de référence une fois codé.

---

## 2. Badge Vigik

**Objectif.** Prendre en charge les badges **Vigik** utilisés par La Poste (et
les services / secours) pour ouvrir les parties communes et les boîtes aux
lettres.

**Ce que l'on sait.** Le SDK définit un type de configuration
`BoksConfigType.LaPosteNfc` appliqué via `SET_CONFIGURATION` (opcode 22). Cela
suggère fortement que l'accès postal Vigik / La Poste est une *configuration* de
la boîte plutôt qu'un badge utilisateur ordinaire, et qu'il est donc distinct du
sujet 1 ci-dessus.

**Ce qu'il faut.** Confirmer, par observation, comment un accès Vigik / La Poste
est provisionné en BLE et ce qu'attend `SET_CONFIGURATION`.

**Matériel.** Présent sur la boîte de référence : son **module clavier a été
upgradé en 2025 pour prendre en charge les badges Vigik**, et c'est ce même
module qui apporte le NFC Mifare du sujet 1. La mention « HW ≥ 4.0 » désigne donc
ce module clavier/NFC — ici ajouté en rétrofit sur une boîte par ailleurs
`Model 2.0` — et les deux sujets badges sont testables de bout en bout sur du
vrai matériel.

**État.** À investiguer. Le chemin protocolaire est inféré depuis les constantes
du SDK, pas encore observé sur un appareil, mais un appareil qui le prend en
charge est disponible pour capture. Rien ne doit être implémenté avant que le
format des trames soit confirmé.

---

## 3. Fiabilisation de la couche Bluetooth

**Objectif.** Moins de connexions échouées et une gestion d'erreur plus claire
sur le chemin `bleak` / `bleak-esphome` / `habluetooth`.

**Points ouverts.**

- **Échecs à faible signal.** À travers le caisson métallique, le lien tourne
  autour de −85 dBm ; des tentatives de connexion échouent parfois et sont
  retentées. Le backoff est en place, mais le chemin d'ouverture par session
  temporaire (utilisé quand le lien n'est pas maintenu) n'a qu'une seule
  validation réelle à ce jour et mérite d'être éprouvé davantage.
- **Cause racine d'`error=-2` en amont.** L'intégration contourne le proxy
  ESPHome qui annonce `REMOTE_CACHING` sans l'honorer (voir la
  [section de dépannage](README.md#dépannage)) en
  vidant le cache GATT à chaque session. Le vrai correctif est dans le firmware
  du proxy ; un patch est préparé pour l'amont.
- **Négociation de l'intervalle de connexion.** Le firmware n'appelle pas
  `updateConnParams`. Négocier un intervalle plus long est le principal levier
  restant sur la consommation quand le lien est maintenu — plus efficace que le
  réglage du keepalive.
- **Épinglage des dépendances.** Suivre les versions de `bleak-esphome` /
  `aioesphomeapi` connues comme bonnes contre cette boîte, pour qu'une mise à
  jour de Home Assistant ne régresse pas le lien en silence.

**État.** En cours, incrémental.

---

## 4. Fiabilisation du code

**Objectif.** Rendre l'intégration assez robuste et maintenable pour un usage
plus large.

**Points ouverts.**

- **Pas encore de suite de tests.** Au minimum : allers-retours
  construction/décodage de trames, la liste blanche d'opcodes (elle doit
  continuer de refuser 16-19 / 22 / 32-33), la validation des PIN, le décodage
  de l'état de porte, et la logique de creux/plateau de batterie.
- **Persistance des valeurs au redémarrage.** Après un redémarrage de Home
  Assistant, les capteurs affichent `unavailable` jusqu'à la première connexion,
  car l'état ne vit qu'en mémoire. `RestoreEntity` sur les capteurs conserverait
  les dernières valeurs connues, comme déjà documenté pour les switches.
- **Cas limites des config/options flow.** Couvrir une référence `!secret`
  cassée, une clé de secret supprimée, et la re-validation au rechargement.
- **Éléments de quality-scale HA.** Téléchargement des diagnostics, chemins
  reauth/reconfigure, typage strict, et CI exécutant `hassfest` + `ruff`.

**État.** En cours.

---

*Si vous comptez travailler sur l'un de ces sujets, ouvrir une issue au
préalable évite les efforts en double — surtout pour les sujets 1 et 2, dont les
détails protocolaires restent à confirmer sur du matériel réel.*
