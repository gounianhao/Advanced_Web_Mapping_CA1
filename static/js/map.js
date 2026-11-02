/*
 * Meet Halfway - map set-up.
 *
 * Draws the OpenStreetMap base map centred on Dublin.
 */
(function () {
  "use strict";

  // Settings sent by Django (MapView.get_context_data -> json_script).
  const config = JSON.parse(document.getElementById("map-config").textContent);

  const map = L.map("map", {
    center: config.center, // [lat, lon]
    zoom: config.zoom,
  });

  // OpenStreetMap base tiles. The tile servers require a Referer header,
  // so the tile images are allowed to send the site's origin.
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    referrerPolicy: "strict-origin-when-cross-origin",
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  // Metric scale bar in the bottom-left corner.
  L.control.scale({ imperial: false }).addTo(map);

  // Shared object so other scripts on the page can use the map.
  window.MeetHalfway = { map: map, config: config };
})();
