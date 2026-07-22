> 🇬🇧 **[English version](../hardware.md)**

# Spécification matérielle

Il vous faut une carte **ESP32-S3** faisant office de proxy Bluetooth entre la
boîte aux lettres et votre réseau WiFi. N'importe quel module ESP32-S3 convient ;
les notes ci-dessous viennent d'un montage réel et vous feront gagner du temps.

## Nécessaire

| Élément | Exigence | Pourquoi |
|---|---|---|
| MCU | **ESP32-S3** | Le firmware cible `esp32s3`. Sa radio et la pile NimBLE dialoguent de façon fiable avec cette boîte. |
| Flash | 4 Mo minimum | L'image fait ~1,3 Mo et le partitionnement est en dual-OTA (deux slots de 1,875 Mo). |
| PSRAM | **inutile** | Le firmware est conçu pour s'en passer. |
| Antenne | **externe, fortement recommandée** | La boîte est un caisson métallique, son signal est faible. Voir [budget radio](#budget-radio). |
| Alimentation | 5 V USB | Une batterie externe suffit pour tester ; préférez une alimentation fixe en permanent. |

## Ports USB — le piège classique

La plupart des cartes ESP32-S3 exposent **deux ports USB-C**, au comportement
différent :

- **Port `COM` / `UART`** (pont CP210x, CH343…) : **utilisez celui-ci**.
  L'auto-reset fonctionne, donc ni le flash ni les logs série ne demandent
  d'appuyer sur des boutons.
- **Port `USB` natif** (périphérique USB du S3) : le flash impose en général
  d'entrer manuellement en mode download — maintenir **BOOT**, appuyer sur
  **RST**, relâcher **BOOT**. La console série peut aussi rester muette selon la
  configuration de la console dans le firmware.

Recommandation : **flashez et déboguez par le port `COM`/UART.** Une fois le
firmware en place, les mises à jour passent en WiFi (OTA), sans câble.

## Budget radio

La radio BLE de la boîte est enfermée dans un **caisson métallique** qui agit
comme une cage de Faraday. Attendez-vous à un signal faible et variable selon le
canal : environ **−83 dBm sur le meilleur canal d'advertising et −92 dBm sur les
autres**, dans une installation typique à quelques mètres à travers une cloison.

Cela fonctionne quand même : connexion et découverte GATT aboutissent à
−83 dBm, et un hôte BlueZ natif a été observé fonctionnel à −93 dBm. Mais la
marge est mince, donc des tentatives de connexion échouent parfois et sont
simplement retentées.

Pour l'améliorer — par ordre d'efficacité :

1. **Visez la façade plastique ou la fente à courrier**, pas la paroi métallique.
2. **Rapprochez-vous.** Diviser la distance par deux gagne environ 6 dB.
3. **Gardez l'antenne verticale**, parallèle à celle de la boîte.
4. **Éloignez l'antenne** du plan de masse de la carte, de la batterie externe et
   de tout métal — un pigtail permet de placer l'antenne seule au meilleur endroit.

Visez **mieux que −80 dBm** pour un lien constamment fiable.

> Augmenter la puissance d'émission BLE du proxy n'améliore **pas** le RSSI
> mesuré : ce chiffre correspond à ce que *vous recevez* de la boîte. Une
> puissance d'émission plus élevée n'aide que le lien retour. Le firmware
> plafonne d'ailleurs l'émission BLE à 9 dBm.

## Carte utilisée en référence

Le montage de référence utilisait un **clone générique d'ESP32-S3 DevKitC-1**
(« N16R8 », 16 Mo de flash, connecteur d'antenne externe u.FL).

⚠️ **Méfiez-vous du marquage PSRAM des clones bon marché.** La carte annonçait
« N16R8 » (8 Mo de PSRAM) mais sa PSRAM est inutilisable : en mode `octal` elle
provoque une exception `IllegalInstruction` et un bootloop, et en mode `quad`
elle remonte *« PSRAM chip is not connected »*. Le module portait la référence
`X01-S3E`, un clone tiers et non un module Espressif authentique. Ici cela ne
coûte rien — le firmware n'a pas besoin de PSRAM et la laisse désactivée — mais
ne comptez pas sur la PSRAM d'une telle carte pour autre chose.

Si vous achetez une carte à connecteur d'antenne externe, vérifiez que l'antenne
y est réellement reliée : certains designs imposent de déplacer une résistance
0 Ω pour basculer de l'antenne PCB vers le connecteur u.FL.
