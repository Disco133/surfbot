// webapp/app.js
const tg = window.Telegram?.WebApp || null;
if (tg) tg.ready();

const map = L.map('map').setView([55, 37], 13);

L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19
}).addTo(map);

// marker
let marker = L.marker(map.getCenter(), {draggable: true}).addTo(map);

document.getElementById('coords').innerText =
  `${marker.getLatLng().lat.toFixed(5)}, ${marker.getLatLng().lng.toFixed(5)}`;

marker.on('dragend', function () {
  const p = marker.getLatLng();
  document.getElementById('coords').innerText =
    `${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}`;
});

map.on('click', function(e) {
  marker.setLatLng(e.latlng);
  document.getElementById('coords').innerText =
    `${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`;
});

// locate
document.getElementById('locateBtn').addEventListener('click', function(){
  if (!navigator.geolocation) return alert('Геолокация не поддерживается');
  navigator.geolocation.getCurrentPosition(function(pos){
    const lat = pos.coords.latitude;
    const lng = pos.coords.longitude;
    marker.setLatLng([lat,lng]);
    map.setView([lat,lng], 12);
    document.getElementById('coords').innerText =
      `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  }, function(err){
    alert('Не удалось получить местоположение: ' + err.message);
  });
});

// choose
document.getElementById('chooseBtn').addEventListener('click', function(){
  const p = marker.getLatLng();
  const date = document.getElementById('surfDate').value;

  const data = {
    lat: p.lat,
    lng: p.lng,
    date: date || null
  };

  if (tg) {
    tg.sendData(JSON.stringify(data));
  } else {
    alert("API недоступно: " + JSON.stringify(data));
  }
});
