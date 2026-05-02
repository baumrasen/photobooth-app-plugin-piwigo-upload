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
                # 1. Wir holen mehr Items (z.B. 50), um den Zeitversatz zu überbrücken
                items = container.mediacollection_service.db.list_items(limit=50)
                
                if items:
                    # 2. Sortierung prüfen
                    # Wir sortieren nach 'created_at'. 
                    # Da es ein datetime-Objekt ist, funktioniert das normalerweise.
                    items.sort(key=lambda x: x.created_at, reverse=True)
                    
                    # DEBUG: Zeig uns mal die Zeiten der ersten 3 Items im Log
                    for i in range(min(3, len(items))):
                        logger.error(f"PIWIGO_TIME_CHECK: Item {i} Zeit: {items[i].created_at}")

                    target_item = None
                    for item in items:
                        if str(item.media_type.value) == actual_type:
                            target_item = item
                            # Wir prüfen, ob das Item "frisch" ist (nicht älter als 5 Minuten)
                            # Das verhindert, dass bei einem Fehler alte Bilder hochgeladen werden
                            break
        
                    if target_item:
                        logger.error(f"PIWIGO: Erfolg! Neueste Collage gefunden. ID: {target_item.id}, Erstellt am: {target_item.created_at}")
                        
                        # Da 'path_full' im Objekt fehlt, müssen wir es über den Service holen:
                        #full_path = container.mediacollection_service.get_item_path_full(target_item.id)
                        
                        # Wir fügen den Pfad temporär an das Objekt an, damit _do_upload ihn findet
                        #target_item.path_full = full_path
                        
                        self._do_upload(target_item)
                    else:
                        logger.error(f"PIWIGO: Kein Item vom Typ {actual_type} in der Liste gefunden.")
                else:
                    logger.error("PIWIGO: Datenbank-Liste ist leer.")
                    
            except Exception as e:
                logger.error(f"PIWIGO_CRITICAL: Fehler bei der Bildsuche: {e}")

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
