document.addEventListener(
    "DOMContentLoaded",
    function () {

        const mapElement =
            document.getElementById(
                "find-pg-map"
            );


        if (!mapElement) {
            return;
        }


        // =========================
        // PG DATA FROM FLASK
        // =========================

        const mapDataElement =
            document.getElementById(
                "pg-map-data"
            );

        let pgData = [];
        let userLatitude = null;
        let userLongitude = null;


        if (mapDataElement) {

            try {

                pgData = JSON.parse(
                    mapDataElement.dataset.pgs
                );

            } catch (error) {

                console.error(
                    "Unable to read PG map data:",
                    error
                );

            }


            // =========================
            // USER LATITUDE
            // =========================

            if (
                mapDataElement.dataset.userLatitude !== ""
            ) {

                userLatitude =
                    parseFloat(
                        mapDataElement.dataset.userLatitude
                    );

            }


            // =========================
            // USER LONGITUDE
            // =========================

            if (
                mapDataElement.dataset.userLongitude !== ""
            ) {

                userLongitude =
                    parseFloat(
                        mapDataElement.dataset.userLongitude
                    );

            }

        }


        // =========================
        // DEFAULT MAP LOCATION
        // =========================

        let defaultLatitude = 30.7333;
        let defaultLongitude = 76.7794;

        let defaultZoom = 11;


        // =========================
        // USE USER LOCATION
        // =========================

        if (
            userLatitude !== null &&
            userLongitude !== null &&
            !Number.isNaN(userLatitude) &&
            !Number.isNaN(userLongitude)
        ) {

            defaultLatitude =
                userLatitude;

            defaultLongitude =
                userLongitude;

            defaultZoom = 13;

        }


        // =========================
        // OTHERWISE USE FIRST PG
        // =========================

        else if (
            pgData.length > 0
        ) {

            defaultLatitude =
                pgData[0].latitude;

            defaultLongitude =
                pgData[0].longitude;

            defaultZoom = 13;

        }


        // =========================
        // CREATE MAP
        // =========================

        const map =
            L.map(
                "find-pg-map"
            ).setView(
                [
                    defaultLatitude,
                    defaultLongitude
                ],
                defaultZoom
            );


        // =========================
        // OPENSTREETMAP
        // =========================

        L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            {
                maxZoom: 19,

                attribution:
                    "&copy; OpenStreetMap contributors"
            }
        ).addTo(map);


        // =========================
        // USER LOCATION
        // =========================

        if (
            userLatitude !== null &&
            userLongitude !== null &&
            !Number.isNaN(userLatitude) &&
            !Number.isNaN(userLongitude)
        ) {

            const userMarker =
                L.marker(
                    [
                        userLatitude,
                        userLongitude
                    ]
                ).addTo(map);


            userMarker.bindPopup(
                `
                <div class="map-popup">

                    <h3>
                        📍 Your Location
                    </h3>

                </div>
                `
            );

        }


        // =========================
        // PG MARKERS
        // =========================

        pgData.forEach(
            function (pg) {

                // =========================
                // CREATE PG MARKER
                // =========================

                const marker =
                    L.marker(
                        [
                            pg.latitude,
                            pg.longitude
                        ]
                    ).addTo(map);


                // =========================
                // RATING
                // =========================

                let ratingHTML = "";


                if (
                    pg.average_rating > 0
                ) {

                    ratingHTML = `
                        <div>
                            ⭐
                            <strong>
                                ${pg.average_rating}
                            </strong>

                            (${pg.review_count}
                            reviews)
                        </div>
                    `;

                }

                else {

                    ratingHTML = `
                        <div>
                            No reviews yet
                        </div>
                    `;

                }


                // =========================
                // DISTANCE
                // =========================

                let distanceHTML = "";


                if (
                    pg.distance !== null &&
                    pg.distance !== undefined
                ) {

                    distanceHTML = `
                        <div>
                            📏
                            ${pg.distance}
                            km away
                        </div>
                    `;

                }


                // =========================
                // GOOGLE MAPS DIRECTIONS
                // =========================

                let directionsURL =
                    "https://www.google.com/maps/dir/?api=1";


                // If student's location exists,
                // use it as the starting point.

                if (
                    userLatitude !== null &&
                    userLongitude !== null &&
                    !Number.isNaN(userLatitude) &&
                    !Number.isNaN(userLongitude)
                ) {

                    directionsURL +=
                        "&origin="
                        +
                        encodeURIComponent(
                            userLatitude
                            +
                            ","
                            +
                            userLongitude
                        );

                }


                // PG location is the destination.

                directionsURL +=
                    "&destination="
                    +
                    encodeURIComponent(
                        pg.latitude
                        +
                        ","
                        +
                        pg.longitude
                    );


                // =========================
                // POPUP HTML
                // =========================

                const popupHTML = `

                    <div class="map-popup">

                        <h3>
                            ${pg.name}
                        </h3>


                        <p>
                            📍
                            ${pg.address}
                        </p>


                        <p>
                            👥
                            ${pg.gender}
                        </p>


                        <p>
                            🛏️
                            ${pg.available_rooms}
                            rooms/beds available
                        </p>


                        ${ratingHTML}


                        ${distanceHTML}


                        <div
                            style="
                                display: flex;
                                gap: 7px;
                                margin-top: 12px;
                                flex-wrap: wrap;
                            "
                        >

                            <!-- View Details -->

                            <a
                                href="/pg/${pg.id}"
                                class="map-view-btn"
                                target="_blank"
                            >
                                View Details
                            </a>


                            <!-- Directions -->

                            <a
                                href="${directionsURL}"
                                target="_blank"
                                rel="noopener noreferrer"
                                style="
                                    display: inline-block;
                                    padding: 8px 12px;
                                    background: #0f766e;
                                    color: white;
                                    text-decoration: none;
                                    border-radius: 6px;
                                    font-size: 13px;
                                    font-weight: 600;
                                "
                            >
                                🧭 Directions
                            </a>

                        </div>

                    </div>

                `;


                // =========================
                // SHOW POPUP
                // =========================

                marker.bindPopup(
                    popupHTML
                );

            }
        );


        // =========================
        // FIT MAP TO MARKERS
        // =========================

        const bounds = [];


        pgData.forEach(
            function (pg) {

                bounds.push(
                    [
                        pg.latitude,
                        pg.longitude
                    ]
                );

            }
        );


        // =========================
        // ADD USER LOCATION TO BOUNDS
        // =========================

        if (
            userLatitude !== null &&
            userLongitude !== null &&
            !Number.isNaN(userLatitude) &&
            !Number.isNaN(userLongitude)
        ) {

            bounds.push(
                [
                    userLatitude,
                    userLongitude
                ]
            );

        }


        // =========================
        // FIT MAP
        // =========================

        if (
            bounds.length > 1
        ) {

            map.fitBounds(
                bounds,
                {
                    padding: [
                        40,
                        40
                    ]
                }
            );

        }

    }
);