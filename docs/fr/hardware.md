> 🇬🇧 **[English version](../hardware.md)**

# Spécification matérielle

Il vous faut une carte faisant office de proxy Bluetooth entre la boîte aux
lettres et votre réseau WiFi. Le montage de référence et le firmware fourni
ciblent l'**ESP32-S3** ; n'importe quel module ESP32-S3 convient, et les notes
ci-dessous viennent d'un montage réel qui vous fera gagner du temps. Deux puces
RISC-V plus récentes méritent aussi l'examen — voir
[Cartes alternatives](#cartes-alternatives-esp32-c6--c5).

## Nécessaire

| Élément | Exigence | Pourquoi |
|---|---|---|
| MCU | **ESP32-S3** | Le firmware cible `esp32s3`. Sa radio et la pile NimBLE dialoguent de façon fiable avec cette boîte. |
| Flash | 4 Mo minimum | L'image fait ~1,3 Mo et le partitionnement est en dual-OTA (deux slots de 1,875 Mo). |
| PSRAM | **inutile** | Le firmware est conçu pour s'en passer. |
| Antenne | **externe, fortement recommandée** | La boîte est un caisson métallique, son signal est faible. Voir [budget radio](#budget-radio). |
| Alimentation | 5 V USB | Une batterie externe suffit pour tester ; préférez une alimentation fixe en permanent. |

## Cartes alternatives (ESP32-C6 / C5)

L'**ESP32-S3** est la référence, validée de bout en bout contre cette boîte.
Deux puces RISC-V plus récentes sont des alternatives intéressantes — toutes
deux imposent de recibler et recompiler le firmware
(`idf.py set-target esp32c6` / `esp32c5`), et aucune n'a encore été validée
contre la boîte ici.

| Puce | Cartes suggérées | Radio | Cœurs | Maturité pour cet usage | Attention |
|---|---|---|---|---|---|
| **ESP32-S3** *(référence)* | DevKitC-1 générique (N16R8) | Wi-Fi 2,4 GHz + BLE 5 | 2× Xtensa (vrai dual-core) | **Validée** de bout en bout | marquage PSRAM trompeur sur les clones — voir [carte de référence](#carte-utilisée-en-référence) |
| **ESP32-C6** | Seeed XIAO ESP32-C6, M5Stack NanoC6 | Wi-Fi 6 2,4 GHz + BLE 5 | 1× RISC-V HP + 1× cœur LP | Silicium mature, bien supporté par ESP-IDF | **des clones de mauvaise qualité circulent** — achetez chez un vendeur fiable |
| **ESP32-C5** | M5Stack Stamp-C5, Seeed XIAO ESP32-C5 | Wi-Fi 6 **bi-bande 2,4 + 5 GHz** + BLE 5 | 1× RISC-V HP + 1× cœur LP | Récente et prometteuse ; support ESP-IDF encore en maturation | avant-garde — outillage et firmware encore mouvants |

> **Pourquoi le C5 est intéressant pour ce projet précisément.** Sur les puces
> mono-bande (S3, C6), le Wi-Fi et le BLE partagent l'unique radio 2,4 GHz et
> doivent se la partager dans le temps — c'est la contention de coexistence qui
> avait rendu un précédent proxy peu fiable. Le C5 est **bi-bande** : placez le
> Wi-Fi sur 5 GHz et la radio 2,4 GHz est laissée entièrement au Bluetooth.
> Vu la minceur du [budget radio](#budget-radio) à travers le caisson
> métallique de la boîte, ne pas partager le temps d'antenne 2,4 GHz est un
> vrai atout.
>
> Le C6, lui, est mono-bande comme le S3 — aucun gain de coexistence — mais il
> est mature et peu cher. Ses « cœurs » ne se comparent pas à ceux du S3 : un
> cœur RISC-V haute performance plus un cœur basse consommation, pas deux cœurs
> applicatifs.

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
