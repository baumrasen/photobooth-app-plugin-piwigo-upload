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
        if not self._config.enabled:
            logger.info("Piwigo Plugin ist deaktiviert.")
            return

        # Den EventBus holen wir uns sicherheitshalber erst beim Start
        from photobooth.container import container
        container.event_bus.subscribe("post_capture", self._on_post_capture)
        logger.info("Piwigo Plugin gestartet und am EventBus registriert.")

    def _on_post_capture(self, media_item):
        if not self._config.enabled:
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
