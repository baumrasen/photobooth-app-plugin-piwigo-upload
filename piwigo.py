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
        logger.error("PIWIGO: Plugin geladen.")

    @hookimpl
    def start(self):
        logger.error("PIWIGO: Plugin gestartet (Warte auf Fotos via Statemachine)...")

    # DAS IST DER ENTSCHEIDENDE HOOK AUS DEINEM CODE-FUND!
    @hookimpl
    def sm_after_transition(self, source, target, event, mediaitem_type):
        # Wir reagieren nur auf 'completed'
        if target.id == "completed":
            if not self._config.enabled:
                return

            from photobooth.container import container
            # Wir warten eine winzige Sekunde, damit die DB sicher geschrieben ist
            import time
            time.sleep(0.5)
            
            # Wir holen das letzte Bild
            latest_item = container.mediacollection_service.get_item_latest()
            
            # Sicherheitscheck: Falls das 'latest' ein altes Bild ist, 
            # könnte man hier noch gegen mediaitem_type prüfen.
            if latest_item:
                self._do_upload(latest_item)

    def _do_upload(self, media_item):
        import json
        from pathlib import Path
        
        raw_path = str(media_item.processed) if media_item.processed else str(media_item.captured_original)
        image_path = str(Path(raw_path).absolute())

        api_endpoint = f"{self._config.api_url}/ws.php?format=json"
        session = requests.Session()

        try:
            # 1. Login
            session.post(api_endpoint, data={
                'method': 'pwg.session.login',
                'username': self._config.username,
                'password': self._config.password
            })
            
            # 2. Upload mit allen Varianten für das Album
            with open(image_path, 'rb') as img:
                cat_id = int(self._config.album_id) # Manche Piwigo Versionen wollen int
                
                payload = {
                    'method': 'pwg.images.addSimple',
                    'category': cat_id,
                    'categories': cat_id,
                    'album': cat_id, # Dritte Namens-Variante
                    'name': media_item.id,
                    'level': 0
                }
                
                response_raw = session.post(api_endpoint, data=payload, files={'image': img})
                
                # JSON-Reparatur
                content = response_raw.text
                content = content[content.find('{'):content.rfind('}')+1]
                response = json.loads(content)

            if response.get('stat') == 'ok':
                image_id = response['result']['image_id']
                
                # JOKER: Falls es immer noch nicht im Album ist, erzwingen wir es jetzt!
                session.post(api_endpoint, data={
                    'method': 'pwg.images.setPrivacy',
                    'image_id': image_id,
                    'level': 0
                })
                # Bild explizit der Kategorie zuweisen
                session.post(api_endpoint, data={
                    'method': 'pwg.images.setInfo',
                    'image_id': image_id,
                    'categories': cat_id,
                    'multiple_value_mode': 'replace'
                })

                media_item.share_url = f"{self._config.api_url}/picture.php?/{image_id}"
                logger.error(f"PIWIGO: ERFOLG! Bild {image_id} hochgeladen und verknüpft.")
            else:
                logger.error(f"PIWIGO: API Fehler: {response}")

        except Exception as e:
            logger.error(f"PIWIGO: Fehler: {e}")

    @hookimpl
    def stop(self):
        pass
