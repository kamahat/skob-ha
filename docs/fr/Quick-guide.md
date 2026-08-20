> 🇬🇧 **[English version](../../Quick-guide.md)**

# Guide de démarrage rapide

Le chemin le plus court pour obtenir un appareil **Boks** fonctionnel dans
Home Assistant. Pour la vue complète — arbitrages, plusieurs boîtes,
dépannage — voir le [README](README.md).

## 1. Débranchez le dongle du fabricant

Le dongle officiel maintient une connexion Bluetooth permanente et rend la boîte
invisible pour tout autre client, dont cette intégration. Débranchez-le en
premier.

## 2. Un proxy Bluetooth NimBLE à portée
Les proxys Bluetooth ESPHome standard (Bluedroid) n'aboutissent jamais à la découverte
sur cette boîte.

Choisir le materiel qui vous convient :  le [guide matériel](hardware.md) 

Compilez le firmware fourni — voir [firmware/nimble-ble-proxy/README-FR.md](../../firmware/nimble-ble-proxy/README-FR.md)
puis laissez l'intégration **ESPHome** de Home Assistant le détecter en mDNS.

## 3. Installez l'intégration

1. HACS → ⋮ → **Dépôts personnalisés** → ajoutez ce dépôt https://github.com/kamahat/skob-ha , catégorie
   **Intégration**.
2. Installez **Boks**, redémarrez Home Assistant.
3. **Paramètres → Appareils et services** : la boîte est détectée
   automatiquement. Sinon, *Ajouter une intégration → Boks*.

Vous avez maintenant l'état de la porte, la batterie, le lien BLE et les
diagnostics — en lecture seule, sans configuration nécessaire.

## 4. (Optionnel) Nommez la boîte

Utile seulement avec plusieurs Boks. **Configurer** → *Identifiant de la
boîte* → la référence imprimée sur la boîte (ex. `F540`). Détails :
[Plusieurs boîtes](README.md#plusieurs-boîtes).

## 5. (Optionnel) Activez l'ouverture à distance

Ajoute un bouton **Ouvrir** — et rien d'autre. **Configurer** → *Code
d'ouverture* → un code permanent de 6 caractères (`0-9`, `A`, `B`),
idéalement via `!secret boks_code1`. Quiconque a accès à votre Home
Assistant peut alors ouvrir la boîte. Détails :
[Ouvrir la porte](README.md#ouvrir-la-porte).

## Réglages par défaut à connaître

- **Connexion maintenue** : éteint. Recommandé — garde la diode Bluetooth de
  la boîte éteinte et économise les piles. Voir
  [Maintenir le lien](README.md#maintenir-le-lien).
- **Intervalle de rafraîchissement** : `0` (désactivé). Réglez-le (en
  minutes) pour des rafraîchissements périodiques, ou pour activer les
  capteurs d'historique d'ouverture — mais lisez d'abord
  [Historique des ouvertures](README.md#historique-des-ouvertures) : lire le
  journal le draine.
- **Jauge de batterie** : ne fonctionne pas avec des piles lithium
  régulées. Activez **Piles rechargeables**
  **Piles à remplacer**, pas le pourcentage. Voir
  [Batterie](README.md#batterie--alcalines-ou-cellules-régulées).

## Un problème ?

Voir [Dépannage](README.md#dépannage) dans le README, ou activez les logs de
debug :

```yaml
logger:
  logs:
    custom_components.boks: debug
```
