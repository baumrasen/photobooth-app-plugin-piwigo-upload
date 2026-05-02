import logging
import requests
import time
import json
from datetime import datetime
from pathlib import Path
from photobooth.plugins import hookimpl
from photobooth.plugins.base_plugin import BasePlugin
from .config import PiwigoConfig

logger = logging.getLogger(__name__)

class Piwigo(BasePlugin[PiwigoConfig]):
    def __init__(self):
        super().__init__()
        self._config = PiwigoConfig()

    @hookimpl
    def photobooth_plugin_config(self):
        return PiwigoConfig

    @hookimpl
    def photobooth_plugin_loaded(self, config: PiwigoConfig):
        self._config = config

    @hookimpl
    def start(self):
        logger.info("PIWIGO: Plugin aktiv und bereit.")

    @hookimpl
    def sm_after_transition(self, source, target, event, mediaitem_type):
        # Wir prüfen auf target.id (das ist der String "completed")
        if target.id == "completed":
            if not self._config.enabled:
                return

            # Typ-Konvertierung (Enum zu String)
            actual_type = mediaitem_type.value if hasattr(mediaitem_type, 'value') else str(mediaitem_type)
            
            # Schalter-Check (z.B. upload_collage)
            config_attr = f"upload_{actual_type}"
            if not getattr(self._config, config_attr, False):
                return

            logger.error(f"PIWIGO: Trigger für {actual_type} erkannt.")

            from photobooth.container import container
            import time
            
            # Etwas Zeit geben, damit die DB-Session im Hauptprogramm commiten kann
            time.sleep(1.5 if actual_type == "collage" else 0.7)
            
            # KORREKTER ZUGRIFF laut deinem Code:
            # Wir holen die neuesten Items über den db-Subservice
            items = container.mediacollection_service.db.list_items(limit=5)
            
            if items:
                # Wir suchen in den letzten 5 Items nach dem passenden Typ
                # (Sicherer als nur das erste zu nehmen, falls die Collage einen Tick später kommt)
                target_item = None
                for item in items:
                    if item.media_type.value == actual_type or str(item.media_type) == actual_type:
                        target_item = item
                        break
                
                if target_item:
                    logger.error(f"PIWIGO: Item gefunden ({target_item.id}). Starte Upload...")
                    self._do_upload(target_item)
                else:
                    logger.error(f"PIWIGO: Kein Item vom Typ {actual_type} in den letzten 5 DB-Einträgen.")
            else:
                logger.error("PIWIGO: Datenbank-Abfrage lieferte keine Ergebnisse.")

    def _do_upload(self, media_item):
        raw_path = str(media_item.processed) if media_item.processed else str(media_item.captured_original)
        image_path = str(Path(raw_path).absolute())

        # Dateiname nach Schema YYYYMMDD_HHMMSS
        ts = media_item.created_at if hasattr(media_item, 'created_at') else datetime.now()
        new_filename = ts.strftime("%Y%m%d_%H%M%S")

        api_endpoint = f"{self._config.api_url}/ws.php?format=json"
        session = requests.Session()

        try:
            session.post(api_endpoint, data={
                'method': 'pwg.session.login', 'username': self._config.username, 'password': self._config.password
            })
            
            with open(image_path, 'rb') as img:
                cat_id = str(self._config.album_id)
                payload = {
                    'method': 'pwg.images.addSimple',
                    'category': cat_id,
                    'categories': cat_id,
                    'name': new_filename,
                    'level': 0
                }
                res = session.post(api_endpoint, data=payload, files={'image': img})
                
                # Robuster JSON-Parser für "Extra Data"
                content = res.text
                data = json.loads(content[content.find('{'):content.rfind('}')+1])

            if data.get('stat') == 'ok':
                img_id = data['result']['image_id']
                # Verknüpfung erzwingen & Titel setzen
                session.post(api_endpoint, data={
                    'method': 'pwg.images.setInfo',
                    'image_id': img_id,
                    'categories': cat_id,
                    'name': new_filename,
                    'multiple_value_mode': 'replace'
                })
                media_item.share_url = f"{self._config.api_url}/picture.php?/{img_id}"
                logger.info(f"PIWIGO: Upload erfolgreich ({new_filename}.jpg)")
            else:
                logger.error(f"PIWIGO: API Fehler: {data}")

        except Exception as e:
            logger.error(f"PIWIGO: Fehler beim Upload: {e}")
