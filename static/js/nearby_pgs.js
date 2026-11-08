// =====================================================
// NEARBY PGs JAVASCRIPT
// =====================================================


// =====================================================
// DETECT STUDENT LOCATION
// =====================================================

function getLocation() {

    const status =
        document.getElementById("location-status");

    const button =
        document.querySelector(".location-btn");


    // Check browser support

    if (!navigator.geolocation) {

        status.innerText =
            "❌ Your browser does not support location detection.";

        return;
    }


    // Show detecting message

    status.innerText =
        "📍 Detecting your location...";

    button.disabled = true;

    button.innerText =
        "Detecting Location...";


    // Get current location

    navigator.geolocation.getCurrentPosition(

        function(position) {

            const latitude =
                position.coords.latitude;

            const longitude =
                position.coords.longitude;


            console.log(
                "Student Latitude:",
                latitude
            );

            console.log(
                "Student Longitude:",
                longitude
            );


            // Redirect to Nearby PGs
            // with location coordinates

            window.location.href =
                "/nearby-pgs?latitude="
                + encodeURIComponent(latitude)
                + "&longitude="
                + encodeURIComponent(longitude);

        },


        function(error) {

            button.disabled = false;

            button.innerText =
                "📍 Detect My Location";


            if (error.code === 1) {

                status.innerText =
                    "❌ Location permission was denied. Please allow location access.";

            }

            else if (error.code === 2) {

                status.innerText =
                    "❌ Your location is currently unavailable.";

            }

            else if (error.code === 3) {

                status.innerText =
                    "❌ Location request timed out. Please try again.";

            }

            else {

                status.innerText =
                    "❌ Unable to detect your location.";
            }

        },


        {
            enableHighAccuracy: true,

            timeout: 15000,

            maximumAge: 0
        }

    );

}



// =====================================================
// MAP INITIALIZATION
// =====================================================

document.addEventListener(
    "DOMContentLoaded",
    function () {

        const mapElement =
            document.getElementById("nearby-map");


        // If map doesn't exist, stop

        if (!mapElement) {
            return;
        }


        // Get student's current location

        const userLatitude =
            parseFloat(
                mapElement.dataset.userLat
            );

        const userLongitude =
            parseFloat(
                mapElement.dataset.userLng
            );


        // Check if location exists

        if (
            Number.isNaN(userLatitude) ||
            Number.isNaN(userLongitude)
        ) {

            mapElement.innerHTML =
                "📍 Please detect your location first.";

            return;
        }


        // =================================================
        // CREATE MAP
        // =================================================

        const map =
            L.map("nearby-map").setView(
                [
                    userLatitude,
                    userLongitude
                ],
                14
            );


        // =================================================
        // OPENSTREETMAP
        // =================================================

        L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            {
                maxZoom: 19,

                attribution:
                    "&copy; OpenStreetMap contributors"
            }
        ).addTo(map);


        // =================================================
        // STUDENT LOCATION MARKER
        // =================================================

        const userMarker =
            L.marker([
                userLatitude,
                userLongitude
            ]).addTo(map);


        userMarker.bindPopup(
            "<strong>📍 Your Location</strong>"
        );


        // =================================================
        // LOCATION CIRCLE
        // =================================================

        L.circle(
            [
                userLatitude,
                userLongitude
            ],
            {
                radius: 200,

                fillOpacity: 0.08
            }
        ).addTo(map);


        // =================================================
        // GET PG MARKERS
        // =================================================

        const pgMarkers =
            document.querySelectorAll(
                ".pg-marker-data-item"
            );


        const allMarkers = [];


        pgMarkers.forEach(
            function (pgData) {

                const latitude =
                    parseFloat(
                        pgData.dataset.lat
                    );

                const longitude =
                    parseFloat(
                        pgData.dataset.lng
                    );

                const name =
                    pgData.dataset.name;

                const address =
                    pgData.dataset.address;

                const gender =
                    pgData.dataset.gender;

                const rooms =
                    pgData.dataset.rooms;

                const distance =
                    pgData.dataset.distance;

                const url =
                    pgData.dataset.url;


                // Skip invalid coordinates

                if (
                    Number.isNaN(latitude) ||
                    Number.isNaN(longitude)
                ) {

                    return;
                }


                // =================================================
                // CREATE PG MARKER
                // =================================================

                const marker =
                    L.marker([
                        latitude,
                        longitude
                    ]).addTo(map);


                // =================================================
                // POPUP
                // =================================================

                const popupContent = `

                    <div class="map-popup">

                        <h3>
                            ${name}
                        </h3>

                        <p>
                            📍 ${address}
                        </p>

                        <p>
                            👥 ${gender}
                        </p>

                        <p>
                            🛏️ ${rooms} rooms available
                        </p>

                        <p>
                            📏 ${distance} km away
                        </p>

                        <a
                            href="${url}"
                            class="map-view-btn"
                        >
                            View PG
                        </a>

                    </div>

                `;


                marker.bindPopup(
                    popupContent
                );


                // Store marker

                allMarkers.push(marker);

            }
        );


        // =================================================
        // MAP VIEW
        // =================================================

        // If PG markers exist, keep the student's
        // location and PGs visible together.

        if (allMarkers.length > 0) {

            const bounds =
                L.latLngBounds([
                    [
                        userLatitude,
                        userLongitude
                    ]
                ]);


            allMarkers.forEach(
                function (marker) {

                    bounds.extend(
                        marker.getLatLng()
                    );

                }
            );


            map.fitBounds(
                bounds,
                {
                    padding: [40, 40]
                }
            );

        }

    }
);