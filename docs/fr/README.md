> 🇬🇧 **[English version](../../README.md)**

# Boks pour Home Assistant

Intégration Home Assistant **en lecture seule** pour la boîte aux lettres
connectée **Boks**, installable via [HACS](https://hacs.xyz/).

La boîte est jointe en Bluetooth LE. Home Assistant est prévenu **à l'instant
où l'état de la porte change** — aucun polling.

| Entité | Type | Remarques |
|---|---|---|
| Porte | `binary_sensor` (`door`) | poussée par la boîte à chaque changement |
| Batterie | `sensor` (%) | poussée sur changement, lue à la connexion |
| Lien BLE | `binary_sensor` (`connectivity`) | diagnostic |
| RSSI | `sensor` (dBm) | diagnostic, désactivé par défaut |
| Firmware / Software | `sensor` | diagnostic, désactivés par défaut |

## Périmètre — lecture seule

Cette intégration **ne fait que lire**. Les seules trames qu'elle émet sont des
**requêtes de statut**, qui servent aussi de keepalive (voir plus bas). Le
constructeur de trames *refuse* tout autre opcode par construction : il est donc
structurellement impossible que l'intégration ouvre la porte, gère des codes PIN
ou modifie la configuration — pas même par erreur. Aucun identifiant du
propriétaire n'est requis ni utilisé.

## Prérequis

1. **Un proxy ou adaptateur Bluetooth à portée de la boîte**, déclaré dans Home
   Assistant. Un proxy sur pile **NimBLE** est fortement recommandé — voir
   [Pourquoi NimBLE](#pourquoi-nimble). Ce dépôt fournit un
   [firmware prêt à compiler](../../firmware/nimble-ble-proxy/) et son
   [guide de compilation](../../firmware/nimble-ble-proxy/README-FR.md).
2. **Le dongle officiel du fabricant doit être débranché.** Il maintient une
   connexion BLE permanente, ce qui rend la boîte invisible pour tout autre
   client, dont cette intégration.

## Installation

### 1. Firmware (une fois)

Compilez et flashez le proxy Bluetooth — voir **[firmware/nimble-ble-proxy/README-FR.md](../../firmware/nimble-ble-proxy/README-FR.md)** et
la **[spécification matérielle](hardware.md)**.

Ajoutez ensuite le proxy à Home Assistant : il s'annonce en mDNS et est détecté
par l'intégration **ESPHome** (API en clair, sans clé de chiffrement). C'est ce
qui permet à Home Assistant de router le Bluetooth vers la boîte.

### 2. Intégration (via HACS)

1. HACS → ⋮ → **Dépôts personnalisés** → ajoutez ce dépôt, catégorie
   **Intégration**.
2. Installez **Boks**, puis redémarrez Home Assistant.
3. **Paramètres → Appareils et services** : la boîte est détectée
   automatiquement (son UUID de service est déclaré dans le manifest). Sinon,
   *Ajouter une intégration → Boks*.

## Pourquoi NimBLE

La boîte ferme toute connexion au bout d'environ **30 secondes** si le client
n'échange pas avec elle. Deux conséquences :

- **La pile BLE est déterminante.** Avec **Bluedroid** — la pile des proxys
  Bluetooth ESPHome standard — la découverte des services GATT n'aboutit jamais
  dans cette fenêtre sur cet appareil : la connexion est coupée avant d'avoir pu
  lire quoi que ce soit. Avec **NimBLE**, la découverte prend environ 6 secondes.
  Un hôte Linux BlueZ natif fonctionne également. D'où le choix de NimBLE pour
  le firmware de ce dépôt.
- **Un keepalive est indispensable.** L'intégration envoie périodiquement une
  requête de statut pour maintenir le lien ; sans elle, la boîte se déconnecte.
  C'est un comportement normal et attendu, pas un contournement de bug.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| La boîte n'est jamais détectée | Dongle officiel encore branché, ou aucun proxy connectable à portée |
| Connexion puis coupure vers 30 s | Keepalive non actif — vérifiez les logs de l'intégration |
| Échecs de connexion fréquents | Signal faible. La boîte est un caisson métallique : visez la façade plastique, voir [matériel](hardware.md) |
| Entités *indisponibles* | Le lien BLE est tombé ; le capteur *Lien BLE*, lui, reste disponible et vous le signale |
| Une connexion échoue après un redémarrage, puis tout va bien | Normal : le cache GATT est purgé au premier essai (voir ci-dessous) |

Activer les logs de debug :

```yaml
logger:
  logs:
    custom_components.boks: debug
```

## Posture d'interopérabilité

Ce projet existe pour qu'un propriétaire de Boks puisse utiliser **son propre
appareil** avec **son propre** système domotique, en local. Il lit des
informations d'état que l'appareil expose sur des characteristics Bluetooth
standard et non authentifiées. Il ne contourne aucune mesure de sécurité,
n'extrait aucun secret et n'interagit pas avec les serveurs du fabricant.

## Crédits et licences

- Intégration Home Assistant et documentation : **GPL-3.0** (voir `LICENSE`).
- Firmware embarqué : travail tiers de **fl4p**, déclaré MIT — voir
  [`NOTICE.md`](../../firmware/nimble-ble-proxy/NOTICE.md) pour l'attribution,
  le commit upstream figé et l'unique correctif de portabilité appliqué.
