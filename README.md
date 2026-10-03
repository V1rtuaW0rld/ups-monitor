# 🖥️ UPS Monitor

[![Docker Image](https://img.shields.io/badge/docker%20hub-virtuaworld%2Fups--monitor-blue.svg?logo=docker)](https://hub.docker.com/r/virtuaworld/ups-monitor)
[![Release](https://img.shields.io/badge/version-2.0-emerald.svg)](https://github.com/V1rtuaW0rld/ups-monitor)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Dashboard web moderne, réactif et autonome pour la surveillance en temps réel de votre onduleur (**Network UPS Tools - NUT**), conçu spécialement pour les onduleurs **EATON** connectés à un **NAS Synology** (ou tout autre serveur NUT).

---

## 💡 Genèse du projet

Ce projet est né suite à l'acquisition d'un onduleur **EATON Ellipse ECO 1600**, qui s'est rapidement heurtée à deux déceptions majeures :

1. **Une limitation matérielle bloquante** :
   L'onduleur ne possède qu'un **seul et unique port USB**. Impossible donc de brancher et de notifier directement plusieurs serveurs, PC ou équipements réseau en cas de coupure de courant.
   *Heureusement*, un **NAS Synology** est capable nativement de reconnaître l'onduleur Eaton branché en USB et d'activer son serveur **NUT (Network UPS Tools)** intégré pour faire office de passerelle / relais réseau pour tout le reste du parc informatique.
2. **Une solution logicielle officielle dépassée** :
   L'application constructeur fournie par Eaton pour surveiller son onduleur laisse grandement à désirer : interface vieillissante, absence d'historique moderne et exploitable, aucune analyse de coût énergétique et impossibilité d'avoir un dashboard web contemporain accessible simplement depuis n'importe quel appareil (PC, smartphone, tablette).

**Alors est née cette application** : offrir une interface moderne, ultra-légère, autonome et instantanée pour monitorer l'onduleur 24h/24 sans aucune dépendance lourde.

---

## ✨ Fonctionnalités clés

* **⚡ Suivi en temps réel & ultra-rapide** :
  * Puissance active consommée (en **Watts**) et puissance apparente (en **VA**).
  * Pourcentage de charge de l'onduleur avec jauge animée et seuils d'alerte (vert, orange, rouge).
  * Niveau de charge de la batterie (%) et autonomie restante estimée en direct (ex: `29 min 22 s`).
  * Tension secteur (230 V) et fréquence réseau (50 Hz).
  * Facteur de puissance paramétrable ($\cos \varphi$, ex: 0.7).
* **🚨 Alerte visuelle de coupure secteur** :
  * Bannière d'alerte dynamique qui apparaît instantanément dès le basculement sur batterie (`OB`), avec décompte de l'autonomie.
* **🤖 Collecteur d'arrière-plan autonome (Worker 24h/24)** :
  * Contrairement aux solutions classiques, la collecte ne dépend pas de l'ouverture d'une page web : un worker dédié interroge le serveur NUT toutes les 5 secondes, calcule la moyenne par minute et l'enregistre en continu.
  * Les données de l'API web sont servies depuis un cache mémoire en **0,2 ms** (zéro latence, zéro appel bloquant).
* **🗄️ Base de données SQLite haute concurrence (Mode WAL)** :
  * Fonctionnement en mode **WAL** (*Write-Ahead Logging*) avec pragmas de concurrence : les lectures ne bloquent plus jamais les écritures (**zéro erreur `database is locked`**).
  * Capable de gérer des centaines de milliers d'enregistrements d'historique sans ralentissement.
* **📈 Graphique interactif fluide avec Downsampling SQL** :
  * Sélecteur de plages temporelles ergonomique : **1h | 6h | 12h | 24h | 48h | 7j | 30j | Tout**.
  * Filtrage et agrégation temporelle intelligente directement exécutés en SQL : le navigateur ne reçoit jamais plus de 300 à 400 points, garantissant un rendu graphique immédiat (< 25 ms) et sans saccades, même sur mobile.
  * Infobulles enrichies (puissance, heure exacte, estimation du coût horaire).
* **📜 Historique automatique des coupures** :
  * Détection et enregistrement de chaque coupure de courant avec heure de début, heure de rétablissement et calcul de la durée exacte.
* **💶 Suivi de la consommation & des coûts** :
  * Calcul de la consommation sur 24h (kWh et coût).
  * Projections mensuelle et annuelle basées sur le tarif de l'électricité (paramétrable dans les réglages).
* **🌓 Thème Sombre & Clair** :
  * Détection automatique des préférences du système et bascule manuelle en un clic (mémorisée localement).

---

## 🚀 Déploiement rapide avec Docker

L'image est **prête à l'emploi et disponible directement sur Docker Hub** sous le tag :
👉 **`virtuaworld/ups-monitor:latest`** (ou `virtuaworld/ups-monitor:2.0`).

### 1. Sur un NAS Synology (Recommandé)

Sur un NAS Synology où l'onduleur Eaton est branché en USB, la meilleure pratique est d'utiliser le mode réseau hôte (`network_mode: host`). Cela permet au conteneur de communiquer directement avec le démon NUT local (`localhost:3493`) sans être bloqué par les restrictions de pare-feu de Docker bridge.

Créez un dossier `/volume1/docker/ups-monitor/` et placez-y le fichier `docker-compose.yml` suivant :

```yaml
services:
  ups-monitor:
    image: virtuaworld/ups-monitor:latest
    container_name: ups-monitor
    network_mode: host
    environment:
      - UPS_HOST=ups@localhost
      - TIMEZONE=Europe/Paris
      - PORT=5010
    restart: unless-stopped
    volumes:
      - ./data:/app/data
```

Lancez simplement le conteneur :
```bash
docker compose up -d
```

Accédez à votre dashboard sur : **`http://<IP_DU_NAS>:5010`** !

---

### 2. Déploiement standard (Autre serveur ou PC distant)

Si le conteneur tourne sur une autre machine que le NAS hébergeant le serveur NUT :

```yaml
services:
  ups-monitor:
    image: virtuaworld/ups-monitor:latest
    container_name: ups-monitor
    environment:
      - UPS_HOST=ups@192.168.0.3   # Remplacer par l'IP de votre serveur NUT
      - TIMEZONE=Europe/Paris
      - PORT=5010
    ports:
      - "5010:5010"
    restart: unless-stopped
    volumes:
      - ./data:/app/data
```

> **Astuce Synology** : Si vous interrogez le NAS depuis une autre machine, pensez à autoriser son adresse IP dans l'interface DSM :
> *Panneau de configuration > Matériel et alimentation > Onduleur > Périphériques DiskStation autorisés*.

---

## ⚙️ Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `UPS_HOST` | `ups@192.168.0.3` | Hôte du serveur NUT au format `nom_ups@adresse:port` (ex: `ups@localhost` ou `ups@192.168.0.3`) |
| `TIMEZONE` | `Europe/Paris` | Fuseau horaire pour l'horodatage des mesures et de l'historique |
| `PORT` | `5010` | Port d'écoute du serveur web |
| `DATA_DIR` | `/app/data` | Répertoire de stockage de la base SQLite et de la configuration |

---

## 🛠️ Développement local

Pour exécuter ou modifier le projet localement sous Python :

```bash
# 1. Cloner le dépôt
git clone https://github.com/V1rtuaW0rld/ups-monitor.git
cd ups-monitor

# 2. Installer les dépendances
pip install -r app/requirements.txt

# 3. Lancer l'application
python app/app.py
```

L'application écoute alors sur `http://localhost:5010`.

---

## 📄 Licence

Ce projet est distribué sous licence MIT. N'hésitez pas à ouvrir une *Issue* ou proposer une *Pull Request* pour toute amélioration !
