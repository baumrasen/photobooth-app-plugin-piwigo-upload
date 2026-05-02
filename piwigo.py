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

#    @hookimpl
#    def get_share_links(self, filepath_local, identifier):
#        # Photobooth fragt: "Welche Links hast du für dieses Bild?"
#        # Wir suchen das Item in der DB, um zu sehen, ob wir eine share_url haben.
#        
#        from photobooth.container import container
#        from uuid import UUID
#        
#        links = []
#        try:
#            # Identifier kommt als UUID oder String
#            item_id = UUID(str(identifier))
#            item = container.mediacollection_service.get_item(item_id)
#            
#            if item and item.share_url:
#                # Wenn wir eine URL in der DB haben, geben wir sie zurück
#                links.append(item.share_url)
#                logger.error(f"PIWIGO: Hook liefert Link zurück: {item.share_url}")
#        except Exception as e:
#            logger.error(f"PIWIGO: Fehler im get_share_links Hook: {e}")
#            
#        return links

    @hookimpl
    def sm_after_transition(self, source, target, event, mediaitem_type):
        if target.id == "completed":
            actual_type = mediaitem_type.value if hasattr(mediaitem_type, 'value') else str(mediaitem_type)
            
            from photobooth.container import container
            import time

            # 1. Wartezeit (Collagen brauchen Zeit zum Speichern!)
            time.sleep(2.5 if actual_type == "collage" else 1.0)

            # 2. Wir nutzen die sichere Methode 'list_items'
            try:
                # Wir holen die letzten 5
                items = container.mediacollection_service.db.list_items(limit=5)
                
                if items:
                    # Wir sortieren nach ID absteigend (Sicherheit geht vor!)
                    # Falls Photobooth UUIDs nutzt, sortieren wir nach dem Dateinamen/Zeit
                    items.sort(key=lambda x: x.id, reverse=True)
                    
                    target_item = None
                    for item in items:
                        # Typ-Check (Collage oder Image)
                        if str(item.media_type.value) == actual_type:
                            target_item = item
                            break # Das ist das NEUESTE dieses Typs!
                    
                    if target_item:
                        logger.error(f"PIWIGO: Gefunden! ID: {target_item.id}, Typ: {actual_type}")
                        self._do_upload(target_item)
                    else:
                        logger.error(f"PIWIGO: Kein Item vom Typ {actual_type} in den letzten 5 gefunden.")
                else:
                    logger.error("PIWIGO: DB-Abfrage ergab keine Items.")
                    
            except Exception as e:
                logger.error(f"PIWIGO: Schwerer Fehler beim DB-Lesezugriff: {e}")

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
