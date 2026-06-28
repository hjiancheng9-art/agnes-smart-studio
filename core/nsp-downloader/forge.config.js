const { MakerZIP } = require('@electron-forge/maker-zip');

module.exports = {
  packagerConfig: {
    name: 'NetSpeedPro',
    executableName: 'NetSpeedPro',
    asar: true,
    extraResource: [
      'resources/aria2c.exe',
      'resources/ffmpeg.exe',
      'resources/yt-dlp.exe',
      'resources/tray-icon.png',
    ],
  },
  makers: [
    new MakerZIP({}, ['win32']),
  ],
  plugins: [],
};
