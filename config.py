from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict
from photobooth import CONFIG_PATH
from photobooth.services.config.baseconfig import BaseConfig


class PiwigoUploadConfig(BaseModel):
    image: bool = Field(
        default=False,
        title="Upload photos",
        description="Enable uploading regular photos to Piwigo."
    )

    collage: bool = Field(
        default=True,
        title="Upload collages",
        description="Enable uploading collages to Piwigo."
    )

    animation: bool = Field(
        default=False,
        title="Upload animations",
        description="Enable uploading animated media to Piwigo."
    )

    video: bool = Field(
        default=False,
        title="Upload videos",
        description="Enable uploading videos to Piwigo."
    )


class PiwigoConnectionConfig(BaseModel):
    api_url: str = Field(
        default="https://your-gallery.example.com",
        title="Piwigo API URL",
        description="Base URL of your Piwigo instance."
    )

    username: str = Field(
        default="admin",
        title="Piwigo username",
        description="Username for the Piwigo API login."
    )

    password: str = Field(
        default="",
        title="Piwigo password",
        description="Password for the Piwigo API login."
    )

    album_id: int = Field(
        default=1,
        title="Target album ID",
        description="Numeric category ID of the target album in Piwigo."
    )


class PiwigoConfig(BaseConfig):
    model_config = SettingsConfigDict(
        title="Piwigo Sync Plugin Configuration",
        json_file=f"{CONFIG_PATH}piwigo.json"
    )

    enabled: bool = Field(
        default=False,
        title="Enable plugin",
        description="Upload media to Piwigo automatically after capture."
    )

    connection: PiwigoConnectionConfig = Field(
        default_factory=PiwigoConnectionConfig,
        title="Piwigo connection",
        description="Connection settings for the Piwigo API."
    )

    upload: PiwigoUploadConfig = Field(
        default_factory=PiwigoUploadConfig,
        title="Upload options",
        description="Enable or disable upload by media type."
    )
