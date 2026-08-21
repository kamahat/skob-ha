# Conception — enregistrement / révocation de badges NFC

> **Statut : conception, non implémenté.** Ce document précède le code, comme
> convenu pour toute fonction d'**écriture**. Rien n'est envoyé à la boîte tant
> que le plan de validation (§5) n'a pas été suivi. Le format des trames est
> établi (dépôt privé `skob`, `docs/02-protocole-ble.md`, § *Enregistrement d'un
> badge NFC*) mais **pas encore vérifié sur cette boîte**.

## 1. Objectif et périmètre

Ajouter deux opérations d'administration :

- **Enregistrer** un badge Mifare « associé » (BoksTAG) — pour qu'il ouvre la boîte.
- **Révoquer** un badge par son UID.

C'est un changement de posture. Aujourd'hui l'intégration est en lecture, plus —
si un code est configuré — l'ouverture. Le constructeur de trames
(`build_frame`) **refuse par construction** tout opcode hors d'un ensemble
restreint (`ALLOWED_TX_OPCODES`), propriété annoncée telle quelle dans le README.
Cette fonction **élargit délibérément** ce périmètre aux opcodes `23/24/25`, et
uniquement quand l'utilisateur a fourni le secret qui les autorise.

## 2. Le secret : Config Key (≠ code d'ouverture)

Ces opérations sont authentifiées par la **Config Key** du propriétaire — un
secret **distinct et plus puissant** que le code d'ouverture PIN :

- le code d'ouverture ouvre la porte, rien d'autre ;
- la Config Key autorise la **gestion des accès** (ici : ajouter/retirer un badge).

Conséquence de sécurité à documenter sans détour : **quiconque a accès à ce Home
Assistant, si une Config Key y est configurée, peut inscrire son propre badge**
sur la boîte. C'est un cran au-dessus de « peut ouvrir ».

### Traitement

- Nouveau champ d'options `CONF_CONFIG_KEY`, sur le modèle exact de
  `CONF_OPEN_CODE` : accepte `!secret <clé>` (résolu par `secret.py`), n'est
  jamais recopié en clair dans `.storage` si passé par référence, **jamais
  journalisé**.
- Validation à la saisie : **exactement 8 caractères hexadécimaux** (règle du SDK,
  `validateConfigKeyFormat`). Rejet sinon, message clair.
- **Gating** : la capacité n'existe que si une Config Key est configurée — comme
  le bouton *Ouvrir* n'existe que si un code est configuré. Pas de Config Key =
  pas de service exposé = allowlist inchangée. L'absence de secret vaut absence
  de capacité.

## 3. Rappel du protocole (format établi)

Trame `[opcode][len][payload][checksum]`, `checksum = (opcode+len+payload) & 0xFF`.
Config Key transmise en **ASCII (8 octets)** ; UID **préfixé par sa longueur**.

```
Enregistrer :
  HOST → SCAN_START (23)         payload [00][configKey:8]
  [ badge présenté au clavier ]
  boîte → NFC_TAG_FOUND (197)    payload [uidLen][uid]        (l'UID à inscrire)
        | ERROR_NFC_SCAN_TIMEOUT (199)  — personne n'a présenté de badge
        | ERROR_NFC_TAG_ALREADY_EXISTS_SCAN (198)  — déjà connu
  HOST → REGISTER_NFC_TAG (24)   payload [configKey:8][uidLen][uid]
  boîte → NFC_TAG_REGISTERED (200)  | ...ERROR_ALREADY_EXISTS (201)

Révoquer :
  HOST → UNREGISTER_NFC_TAG (25) payload [configKey:8][uidLen][uid]
  boîte → NFC_TAG_UNREGISTERED (202)
```

## 4. Détection de capacité

La boîte annonce `nfcTagRegister` dans les `pcb.capabilities` **côté cloud** —
non lisible en BLE. Le SDK mentionne « HW ≥ 4.0 », mais cette boîte renvoie
`Model Number 2.0` tout en faisant tourner le NFC : cet indicateur **n'est pas
fiable** ici (déjà établi). On ne s'y fie donc pas.

**Décision : ne pas sonder le matériel.** On gate sur la présence de la Config
Key, et on laisse la boîte elle-même trancher via ses réponses d'erreur
(`ERROR_UNAUTHORIZED` 225 si la clé est mauvaise, silence/refus si l'opcode n'est
pas honoré). Le plan de validation §5 confirme d'abord que la boîte les honore.

## 5. Plan de validation — échelle non destructive d'abord

Le format est établi mais **jamais rejoué** sur cette boîte, et le dongle
officiel en était peut-être le seul émetteur en pratique. On valide **par
paliers**, du non destructif vers le destructif, via le bastion, chaque palier
devant réussir avant le suivant :

- **Palier 0a — clé bidon, aucun badge. ✅ FAIT (2026-08-21).** Envoyer
  `SCAN_START (23)` avec une Config Key **volontairement invalide** (`AABBCCDD`),
  sans présenter de badge. **Résultat : la boîte répond `225 ERROR_UNAUTHORIZED`**
  (`e1 00 e1`). Cela prouve, sans aucun secret ni changement d'état : la boîte
  **honore l'opcode 23**, **valide la Config Key en amont**, **comprend notre
  encodage de trame** (sinon `224`/`226`), et la fonction **n'est pas réservée au
  dongle** (réponse obtenue sur une connexion proxy en clair, non appairée). La
  faisabilité est établie. Harnais : `boks-esphome-test/palier0_scanstart.py` sur
  le bastion (n'émet QUE l'opcode 23).
- **Palier 0b — vraie clé. ⚠️ BLOQUÉ (2026-08-21).** `SCAN_START (23)` avec la
  **vraie** Config Key renvoie encore `225 UNAUTHORIZED`, avant même tout badge
  (la boîte valide donc l'auth **en amont** du scan). Diagnostics menés :
  - **La valeur de la clé est correcte.** Re-fetchée en direct via l'API compte
    (`GET /api/pcbs/<pcbMac>/configuration-key`) : **identique** à celle du
    fichier. Le compte confirme aussi `scanNfcLaposteEnabled=true`.
  - **L'encodage n'est pas en cause.** Testé en ASCII-8, hex-4-octets et
    ASCII-minuscules : les trois → `225` (et jamais `226`, donc la trame est
    bien parsée). Le SDK indique par ailleurs que clé dérivée de la Master Key
    et clé directe sont *la même* Config Key.
  - **Le proxy ne sait pas appairer.** `bluetooth_proxy_feature_flags=39` (bit
    `PAIRING`=8 absent) ; `connect(pair=True)` → `NotImplementedError`. Notre
    lien BLE via le proxy est donc **non bondé**.

  **Hypothèse dominante :** les opérations d'admin authentifiées par Config Key
  exigent un **lien BLE appairé/bondé** — ce que le dongle officiel établit et
  que le proxy ne fait pas. Cela expliquerait d'un coup le `225` (auth refusée
  sur lien non bondé) **et** le mystère de longue date de la diode Bluetooth. Le
  SDK n'expose aucune étape d'authentification séparée (juste `connect()` puis
  `registerNfcTag()`), donc rien à « rejouer » côté application : la différence
  est au niveau lien.

  **Non prouvé :** que le bonding lève le `225`. Le confirmer exige un central
  capable d'appairer (le Pi4 arbiter + noble, **hors ligne** au moment du test),
  ou un firmware proxy avec support `PAIRING`. À reprendre quand l'un des deux
  est disponible.

  **Conséquence côté intégration :** le volet **lecture** (porte, batterie,
  historique, capteurs d'ouverture) fonctionne sans bonding via le proxy, et
  l'ouverture à distance aussi (elle utilise un PIN à usage unique, pas la Config
  Key). Seules les **écritures admin** (register/unregister NFC) semblent
  requérir un lien bondé, hors de portée du chemin proxy actuel.

- **Palier 0c — même 225 via un central natif (noble/BlueZ). ⛔ (2026-08-21).**
  Rejoué depuis le Pi4 arbiter (noble, BLE natif) avec la vraie Config Key :
  **encore `225`**, immédiat, avant tout badge. Donc **ce n'est pas un artefact
  du proxy** : la Config Key seule, sur un lien BLE ordinaire, ne suffit pas —
  ni via le proxy, ni via BlueZ. (Un `connectAsync` noble ne force pas le bond ;
  BlueZ ne bonde que si une opération l'exige, ce que l'écriture ne fait pas.)

### Analyse du dump du dongle (2026-08-21) — ce qui est établi, et une erreur corrigée

> **Correction.** Une version antérieure de cette section (et le rapport de dump
> §8) attribuait à la **session BLE avec la boîte** un handshake **SRP + ECDH +
> AES**. **C'est faux.** Vérification faite sur les strings : ces primitives
> appartiennent à l'**ESP-IDF protocomm** (`PROTOCOMM_SECURITY_SESSION_EVENT`,
> `SEC2_MSG_TYPE__S2Session_Command`, `handle_session_command1`, « *Invalid
> username* »…), c.-à-d. la sécurité du **provisioning WiFi** (téléphone ↔
> dongle), **pas** le dialogue avec la boîte. Fausse piste.

Ce qui **est** établi par le dump :

- **Le canal boîte est en clair.** `open_boks` loggue « *Sending door open request
  with code %s* » : le dongle **relaie un code d'ouverture en clair** (le code
  vient du cloud par MQTT `boks/<id>/door`). C'est exactement notre format
  `OPEN_DOOR` plaintext, qui marche. Donc pas de chiffrement applicatif côté boîte.
- **Le dongle gère bien register + VIGIK.** Strings `NFC_TAG_REGISTERING_SCAN`,
  `nfcTag`, `laposte_service_universel`, `laposte_autres_services`. Il **est**
  la voie de ces opérations.
- **Le dongle embarque tout NimBLE SMP** (chiffrement/bonding) et traite les
  « *encryption change event* ». La table d'erreurs GATT inclut
  `BLE_ATT_ERR_INSUFFICIENT_ENC` (« *requires encryption before write* »).

**Ce qui n'est PAS résolu :** comment le dongle authentifie register/VIGIK auprès
de la boîte. Le flux de connexion loggé est `connect → discover → subscribe`, sans
étape de chiffrement explicite tracée — mais l'absence de *string* ne prouve pas
l'absence d'appel. Deux candidats subsistent :
1. **Lien chiffré/bondé requis pour l'admin.** La boîte renverrait un `225`
   applicatif tant que le lien n'est pas chiffré (l'ouverture, elle, marche non
   bondée car validée par un code). Cohérent avec le SMP présent côté dongle et
   le `INSUFFICIENT_ENC`. **Non testé** : ni le proxy ni notre `connectAsync`
   noble n'ont établi de lien bondé.
2. **Un credential différent** attaché à la commande register (pas la seule
   Config Key en payload).

**Trancher (1) est empirique et rapide** : établir un lien **bondé** (appairage
explicite `bluetoothctl` sur le Pi4) puis rejouer `SCAN_START`. Si le `225` tombe,
c'est le bonding — et register + VIGIK deviennent faisables en local. Sinon, il
faut du désassemblage fonctionnel du chemin de commande boîte (Xtensa sans
symboles — lent). L'appairage **écrit un bond dans la boîte** (réversible ;
n'affecte ni codes ni Master Key).

### Test d'appairage explicite (2026-08-21) — négatif, et il tranche

Appairage tenté depuis le Pi4 (`bluetoothctl`, agent Just Works) : la boîte est
**atteinte et connectée** (nom `CD05E365D67`) mais l'appairage **échoue** —
`auth failed status 0x05 (Authentication Failed)`, `Paired: no / Bonded: no`. La
boîte **refuse le Just Works** (elle voudrait un appairage *authentifié* /
passkey qu'on ne sait pas fournir).

Recoupé avec une **re-inspection ciblée du NVS du dongle** : **aucun
enregistrement de bond NimBLE** (`our_sec`/`peer_sec`/`peer_dev_rec` absents ;
les « CSRK/IRK/NIMBLE » repérés étaient des sous-chaînes fortuites dans des clés
WiFi aléatoires). **Le dongle ne stocke donc pas de bond avec la boîte** → il ne
bonde pas non plus. **Le bonding n'est pas le mécanisme d'auth admin.**

### Conclusion honnête de l'investigation

Après un tour complet — Config Key (valeur correcte, confirmée cloud), encodage
(correct), proxy vs noble (les deux `225`), SRP (fausse piste = provisioning),
canal boîte (en clair), bonding (boîte refuse l'appairage, dongle sans bond) —
**l'auth des opcodes d'admin `22-25` n'est pas reproductible avec ce qu'on
détient**, et **n'est ni du chiffrement applicatif ni du bonding BLE**. Deux
lectures restantes, toutes deux hors de portée immédiate :

1. Le dongle attache aux commandes d'admin un **credential** qu'on n'a pas encore
   isolé (nécessiterait du **désassemblage fonctionnel** du chemin de commande
   boîte — Xtensa sans symboles, lent et incertain).
2. L'enregistrement de tag est **côté usine / cloud**, le dongle ne faisant que
   **relayer les événements** (`NFC_TAG_REGISTERING_SCAN` reçu comme *log*, pas
   émis comme commande) — auquel cas il n'existe **pas** de voie BLE propriétaire.

**Décision : écriture NFC (register/unregister) et activation VIGIK PARQUÉES,
sans voie locale connue à ce jour.** Le volet **lecture** reste livré et couvre le
besoin quotidien (détection d'usage). Réouverture possible seulement via (a)
désassemblage fonctionnel approfondi, ou (b) capture MITM d'un provisioning réel
de tag (commander un tag et observer), ou (c) l'API cloud (à rebours du local).
- **Palier 1 — badge de test jetable.** Enregistrer un badge Mifare neuf
  (`24` → `200`), vérifier physiquement qu'il ouvre la boîte, puis le révoquer
  (`25` → `202`), vérifier qu'il n'ouvre plus. Jamais sur un badge en service.
- **Palier 2 — activation.** Seulement après 0 et 1, on active la fonction.

Aucun `REGISTER`/`UNREGISTER` n'est émis sur un badge réel du foyer pendant la
validation.

## 6. Machine à états et échecs à mi-parcours

L'enregistrement est **stateful et borné dans le temps**. On généralise le
pattern existant d'`async_open_door` (écrire, puis attendre une réponse via une
`Future` résolue dans `_on_app_notify`, avec timeout) :

- **Un seul flux à la fois** — un `asyncio.Lock` ; un enregistrement en cours
  refuse un second.
- `SCAN_START` → attente de `{197, 198, 199}` avec timeout (généreux : il faut le
  temps de présenter le badge, ex. 30–45 s). `199` ou timeout → erreur claire
  « aucun badge présenté », état propre.
- Sur `197` → `REGISTER_NFC_TAG` avec l'UID reçu → attente de `{200, 201}` avec
  timeout plus court. `201` → « badge déjà enregistré » (pas une erreur dure).
- **Annulation / sortie propre** : à la fin du flux (succès, échec, timeout), on
  ne laisse ni scan pendant ni demi-connexion. La boîte fait elle-même expirer
  son mode scan (`199`), on n'a donc pas à « annuler » côté boîte, mais on remet
  notre état interne à zéro dans un `finally`.
- Les erreurs remontent en `HomeAssistantError` (comme `BoksOpenError`) pour
  s'afficher à l'utilisateur, pas s'enterrer dans le journal.

## 7. Surface Home Assistant — décision à valider

Une opération d'administration interactive et occasionnelle s'accommode mal
d'entités toujours visibles. Deux options :

| | A — Actions (services) | B — Entités |
|---|---|---|
| Forme | `boks.register_nfc_tag`, `boks.unregister_nfc_tag` | bouton « Enregistrer », capteur UID trouvé, champ texte + bouton « Révoquer » |
| Ergonomie | naturelle pour un geste d'admin ; appelable depuis Outils de dev / scripts ; renvoie l'UID inscrit | plusieurs entités d'écriture en permanence sur la page d'un contrôle d'accès |
| Page appareil | reste propre | encombrée, contrôles d'écriture toujours là |
| Multi-étapes | encapsulé dans l'action (scan → attente → register) | exposé à l'utilisateur (deux clics + attente) |

**Recommandation : A (services)**, enregistrés **seulement si** une Config Key est
présente. `register_nfc_tag` fait scan-start + attend + inscrit le premier badge
trouvé et renvoie son UID. `unregister_nfc_tag` prend l'UID en paramètre requis.
Cohérent avec la posture « écritures explicites, opt-in, jamais par défaut ».

## 8. Changement de l'allowlist et honnêteté du README

- `ALLOWED_TX_OPCODES` est un `frozenset` module-level, propriété de sécurité
  **statique** vantée dans le README. On préserve la propriété « refuse par
  construction » : les opcodes `23/24/25` ne sont autorisés dans `build_frame`
  **que lorsqu'une Config Key est configurée** (autorisation contextuelle, pas
  un simple ajout à l'ensemble global).
- Le README doit changer **honnêtement** : aujourd'hui il affirme que la gestion
  de codes, la configuration et le provisioning « restent hors d'atteinte ». Avec
  cette fonction, l'**enregistrement de badge** devient atteignable *quand une
  Config Key est fournie*. À écrire noir sur blanc, avec l'avertissement §2 sur
  le pouvoir de la Config Key. Les opcodes `16-19 / 22 / 32-33` restent, eux,
  hors d'atteinte.

## 9. Tests

- Encodage : `build_*` produit **exactement** les octets capturés (23/24/25),
  Config Key en ASCII, UID préfixé, checksum.
- Validation Config Key (8 hex) et UID (longueur).
- Machine à états sur notifications simulées : 197→register→200 ; 199→erreur ;
  201→« déjà là » ; timeout à chaque attente.
- Gating : aucun service enregistré sans Config Key ; `build_frame` refuse
  23/24/25 sans Config Key.

## 10. Déploiement

Derrière la Config Key. Paliers §5 sur la vraie boîte via le bastion **avant**
toute annonce. Bump de version à la livraison, entrée CHANGELOG mentionnant
l'élargissement de périmètre.

## Décisions ouvertes (à trancher avant implémentation)

1. **Surface** : services (recommandé) vs entités ?
2. **Plan de validation** : on commence par le palier 0 (non destructif) ?
3. **Gating** : uniquement sur présence de la Config Key (recommandé) ?
