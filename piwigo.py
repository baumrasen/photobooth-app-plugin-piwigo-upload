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
        """Wird von PluginEventHooks nach jedem Zustandswechsel gerufen."""
        
        # Wir reagieren nur, wenn die Statemachine 'completed' erreicht
        # target.id ist laut deinem Code 'completed'
        if target.id == "completed":
            logger.error(f"PIWIGO: Statemachine ist 'completed'. Starte Upload-Check...")
            
            if not self._config.enabled:
                return

            # Wir brauchen das neueste Medien-Item aus der Datenbank
            from photobooth.container import container
            latest_item = container.mediacollection_service.get_item_latest()
            
            if latest_item:
                self._do_upload(latest_item)
            else:
                logger.error("PIWIGO: Kein Bild in der Datenbank gefunden!")

    def _do_upload(self, media_item):
        import json
        
        # 1. Absoluten Pfad sicherstellen
        # Falls der Pfad relativ ist (wie im Log), machen wir ihn absolut
        raw_path = str(media_item.processed) if media_item.processed else str(media_item.captured_original)
        from pathlib import Path
        image_path = str(Path(raw_path).absolute())

        logger.error(f"PIWIGO: Upload startet! Absoluter Pfad: {image_path}")

        api_endpoint = f"{self._config.api_url}/ws.php?format=json"
        session = requests.Session()

        try:
            # Login
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
                    'name': getattr(media_item, 'id', 'upload') 
                }
                response_raw = session.post(api_endpoint, data=payload, files={'image': img})
                
                # REPARATUR FÜR "EXTRA DATA":
                # Wir nehmen nur den Teil bis zur letzten schließenden Klammer }
                content = response_raw.text
                last_brace = content.rfind('}')
                if last_brace != -1:
                    content = content[:last_brace+1]
                
                response = json.loads(content)

            if response.get('stat') == 'ok':
                image_id = response['result']['image_id']
                # QR-Code URL setzen
                media_item.share_url = f"{self._config.api_url}/picture.php?/{image_id}"
                logger.error(f"PIWIGO: ERFOLG! Bild-ID: {image_id}, URL: {media_item.share_url}")
            else:
                logger.error(f"PIWIGO: API meldet Fehler: {response}")

        except Exception as e:
            logger.error(f"PIWIGO: Fehler beim Upload-Prozess: {e}")
            # Falls vorhanden, zeige die rohe Antwort für das Debugging
            if 'response_raw' in locals():
                logger.error(f"PIWIGO: Rohe API-Antwort: {response_raw.text[:100]}")

    @hookimpl
    def stop(self):
        pass
