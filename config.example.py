from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict
from photobooth import CONFIG_PATH
from photobooth.services.config.baseconfig import BaseConfig

class PiwigoConfig(BaseConfig):
    model_config = SettingsConfigDict(
        title="Piwigo Sync Plugin Config",
        json_file=f"{CONFIG_PATH}piwigo.json"
    )

    enabled: bool = Field(
        default=False,
        title="Plugin aktivieren",
        description="Bilder nach der Aufnahme automatisch zu Piwigo hochladen."
    )

    api_url: str = Field(
        default="https://deine-galerie.de",
        title="Piwigo URL",
        description="Die Basis-URL deiner Piwigo-Instanz."
    )

    username: str = Field(
        default="dein-benutzername",
        title="Benutzername"
    )

    password: str = Field(
        default="dein-passwort",
        title="Passwort"
    )

    album_id: int = Field(
        default=1,
        title="Album ID",
        description="Die numerische ID (category_id) des Zielalbums."
    )