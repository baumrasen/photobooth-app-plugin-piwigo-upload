import logging
import requests
from photobooth.plugins import hookimpl
from photobooth.plugins.base_plugin import BasePlugin
from .config import PiwigoConfig

logger = logging.getLogger(__name__)

class Piwigo(BasePlugin[PiwigoConfig]):
    def __init__(self):
        super().__init__()
        self._config: PiwigoConfig = PiwigoConfig()

    @hookimpl
    def photobooth_plugin_config(self):
        return PiwigoConfig

    @hookimpl
    def photobooth_plugin_loaded(self, config: PiwigoConfig):
        self._config = config
        logger.info("Piwigo Plugin geladen.")

    @hookimpl
    def start(self):
        logger.error("PIWIGO: start() wurde aufgerufen!")
        
        if not self._config.enabled:
            logger.error("PIWIGO: Plugin ist deaktiviert!")
            return

        from photobooth.container import container
        
        # SPIONAGE: Wir listen alle Attribute des Containers auf
        attrs = dir(container)
        logger.error(f"PIWIGO: Container Attribute: {attrs}")

        # Wir suchen gezielt nach etwas, das 'event' im Namen hat
        event_related = [a for a in attrs if "event" in a.lower()]
        logger.error(f"PIWIGO: Event-Verdächtige Attribute: {event_related}")

        # Versuch einer automatischen Zuweisung, falls wir einen Treffer haben
        if event_related:
            target = event_related[0]
            self._event_bus = getattr(container, target)
            self._event_bus.subscribe("post_capture", self._on_post_capture)
            logger.error(f"PIWIGO: Versuche Abo auf Attribut '{target}'")
        else:
            logger.error("PIWIGO: Absolut nichts mit 'event' im Container gefunden!")

    def _on_post_capture(self, media_item):
        # TEST-LOG: Diese Zeile muss erscheinen, sobald ein Foto fertig ist!
        logger.info(f"EVENT EMPFANGEN: post_capture getriggert für {media_item.filename}")

        if not self._config.enabled:
            logger.warning("Piwigo Upload übersprungen: Plugin ist in Config deaktiviert!")
            return

        image_path = media_item.path_full
        api_endpoint = f"{self._config.api_url}/ws.php?format=json"

        try:
            session = requests.Session()
            # 1. Login
            session.post(api_endpoint, data={
                'method': 'pwg.session.login',
                'username': self._config.username,
                'password': self._config.password
            })
            
            # 2. Upload
            with open(image_path, 'rb') as img:
                payload = {
                    'method': 'pwg.images.addSimple',
                    'category': self._config.album_id,
                    'name': media_item.filename
                }
                response = session.post(api_endpoint, data=payload, files={'image': img}).json()

            if response.get('stat') == 'ok':
                image_id = response['result']['image_id']
                # URL für den QR-Code setzen
                media_item.share_url = f"{self._config.api_url}/picture.php?/{image_id}"
                logger.info(f"Piwigo Upload erfolgreich: {media_item.share_url}")
            else:
                logger.error(f"Piwigo API Fehler: {response}")

        except Exception as e:
            logger.error(f"Fehler im Piwigo Plugin: {e}")

    @hookimpl
    def stop(self):
        logger.info("Piwigo Plugin gestoppt.")
