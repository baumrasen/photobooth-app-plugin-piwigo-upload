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
        import json
        import requests
        from pathlib import Path
        from datetime import datetime
        from photobooth.container import container

        logger.error("PIWIGO_DEBUG: Funktion _do_upload wurde betreten.")

        try:
            raw_path = str(media_item.processed) if media_item.processed else str(media_item.captured_original)
            image_path = str(Path(raw_path).absolute())
            logger.error(f"PIWIGO_DEBUG: Pfad ermittelt: {image_path}")

            api_endpoint = f"{self._config.api_url}/ws.php?format=json"
            session = requests.Session()
            # Falls dein Zertifikat zickt (selbstsigniert), verify=False
            session.verify = True 

            # 1. Login
            logger.error(f"PIWIGO_DEBUG: Login-Versuch für User: {self._config.username}")
            login_res = session.post(api_endpoint, data={
                'method': 'pwg.session.login',
                'username': self._config.username,
                'password': self._config.password
            }, timeout=10)
            logger.error(f"PIWIGO_DEBUG: Login-Response Status: {login_res.status_code}")

            # 2. Upload
            logger.error("PIWIGO_DEBUG: Öffne Datei für Upload...")
            with open(image_path, 'rb') as img:
                # Debug: Was steht in der config?
                album_id_str = str(self._config.album_id)
                logger.error(f"PIWIGO_DEBUG: Versuche Upload in Album-ID: '{album_id_str}'")

                payload = {
                    'method': 'pwg.images.addSimple', # Falls das nicht klappt, versuche 'pwg.images.upload'
                    'category': album_id_str,
                    'name': datetime.now().strftime("%Y%m%d_%H%M%S"),
                    'format': 'json' # Wichtig, damit wir eine lesbare Antwort bekommen
                }

                logger.error(f"PIWIGO_DEBUG: Sende POST an {api_endpoint} mit Payload: {payload}")
                
                try:
                    response_raw = session.post(api_endpoint, data=payload, files={'image': img}, timeout=30)
                    
                    # Logge den HTTP Status und den rohen Text der Antwort
                    logger.error(f"PIWIGO_DEBUG: HTTP Status: {response_raw.status_code}")
                    logger.error(f"PIWIGO_DEBUG: Raw Response: {response_raw.text}")

                    # Versuche das JSON zu parsen für detaillierte Fehlermeldungen
                    try:
                        res_json = response_raw.json()
                        if res_json.get('stat') != 'ok':
                            logger.error(f"PIWIGO_ERROR: Piwigo meldet Fehler: {res_json.get('err')} - {res_json.get('message')}")
                        else:
                            logger.error(f"PIWIGO_DEBUG: Erfolg! Image ID: {res_json.get('result', {}).get('image_id')}")
                    except Exception as json_err:
                        logger.error(f"PIWIGO_DEBUG: Antwort ist kein gültiges JSON: {json_err}")

                except Exception as e:
                    logger.error(f"PIWIGO_DEBUG: Kritischer Fehler beim Request: {str(e)}")

            # 3. JSON Parser
            content = response_raw.text
            logger.error(f"PIWIGO_DEBUG: Roh-Antwort (erste 50 Zeichen): {content[:50]}")
            
            # Extrahiere JSON
            start = content.find('{')
            end = content.rfind('}') + 1
            if start == -1 or end == 0:
                logger.error(f"PIWIGO_DEBUG: Kein JSON in Antwort gefunden! Inhalt: {content}")
                return

            data = json.loads(content[start:end])
            logger.error(f"PIWIGO_DEBUG: JSON erfolgreich geparst. Status: {data.get('stat')}")

            if data.get('stat') == 'ok':
                # Anstatt des Links zum Einzelbild nehmen wir den Album-Link
                # Den Link am besten auch in die Plugin-Config (piwigo.py) packen 
                # oder hier hart codieren:
                
                from photobooth.container import container
                container.mediacollection_service.update_item(media_item)
                
                logger.info(f"PIWIGO: QR-Code from custom url")
            else:
                logger.error(f"PIWIGO_DEBUG: Piwigo meldet Fehler: {data}")

        except Exception as e:
            # Hier loggen wir den EXAKTEN Fehler-Typ und die Nachricht
            logger.error(f"PIWIGO_CRITICAL: Fehler in _do_upload: {type(e).__name__} - {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

