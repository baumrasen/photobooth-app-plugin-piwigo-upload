# photobooth-app-plugin-piwigo-upload

A plugin for the photobooth-app to automatically upload captured media (photos, collages, animations, videos) to a Piwigo gallery.

## Installation

1. Copy the plugin folder to your photobooth data directory. The folder **must** be named `data/plugins/piwigo`.
   - Example: If your photobooth data is in `/home/user/photobooth-data`, copy the plugin to `/home/user/photobooth-data/plugins/piwigo`.

2. Restart the photobooth application to load the plugin.

## Configuration

The plugin is configured via the photobooth web interface under the plugin settings. The configuration file is stored as `piwigo.json` in the photobooth config directory.

### Main Settings
- **Enable plugin**: Enable or disable the plugin globally.
- **Piwigo connection**:
  - **Piwigo API URL**: Base URL of your Piwigo instance (e.g., `https://your-gallery.example.com`).
  - **Piwigo username**: Username for API login.
  - **Piwigo password**: Password for API login.
  - **Target album ID**: Numeric category ID of the album where images should be uploaded.

### Upload Options
- **Upload photos**: Enable uploading of regular photos.
- **Upload collages**: Enable uploading of collages (default: enabled).
- **Upload animations**: Enable uploading of animated media (GIFs, etc.).
- **Upload videos**: Enable uploading of videos.

## How it Works

- When a photo, collage, animation, or video is captured and the state machine reaches "completed", the plugin checks if upload is enabled for that media type.
- If enabled, it starts an asynchronous upload process to avoid blocking the photobooth UI.
- The plugin waits for the media file to be fully saved, then uploads it to Piwigo using the API.
- Upon successful upload, a share URL is set on the media item for QR code generation.

## Requirements

- Photobooth-app with plugin support.
- A running Piwigo instance with API access.
- Network connectivity between photobooth and Piwigo server.

## Troubleshooting

- Check the photobooth logs for "PIWIGO:" messages.
- Ensure the Piwigo API URL is correct and accessible.
- Verify username/password and album ID in Piwigo.
- Make sure the plugin folder is correctly named and placed.

## License

See LICENSE file.
