async function fetchUPS() {
    const res = await fetch("/api/ups");
    const data = await res.json();
    const container = document.getElementById("ups-content");
    container.innerHTML = "";
    container.classList.remove("alert-battery");

    if (data.error) {
        container.innerHTML = `<p>Erreur : ${data.error}</p>`;
        return;
    }

    const keysToShow = [
        "battery.charge", "battery.runtime", "ups.status",
        "ups.load", "outlet.power", "output.voltage"
    ];

    keysToShow.forEach(key => {
        if (data[key]) {
            const p = document.createElement("p");
            let value = data[key];

            if (key === "battery.charge") {
                value += " %";
            }
            if (key === "battery.runtime") {
                const seconds = parseInt(value);
                const minutes = Math.floor(seconds / 60);
                const secs = seconds % 60;
                value = `${minutes}min ${secs}s d'autonomie estimée`;
            }
            if (key === "ups.status") {
                if (value === "OL") {
                    value = "Online ✅";
                } else {
                    value = "⚠️ Batterie activée (" + value + ")";
                    container.classList.add("alert-battery");
                }
            }

            p.textContent = `${key}: ${value}`;
            container.appendChild(p);
        }
    });

    // 🔢 Conso estimée
    const nominalVA = parseInt(data["ups.power.nominal"]);
    const loadPercent = parseInt(data["ups.load"]);
    const pfSelector = document.getElementById("pf-selector");
    const factor = parseFloat(pfSelector.value);

    if (!isNaN(nominalVA) && !isNaN(loadPercent)) {
        const va = nominalVA * (loadPercent / 100);
        const watts = Math.round(va * factor);

        container.innerHTML += `
            <p>Charge UPS : ${loadPercent}%</p>
            <p>Puissance nominale : ${nominalVA} VA</p>
            <p>Conso estimée : ${va.toFixed(1)} VA ≈ ${watts} W</p>
        `;

        // 💰 Estimation mensuelle instantanée
        const price = parseFloat(document.getElementById("price-input").value);
        const unit = document.getElementById("unit-input").value || "€";

        if (!isNaN(price)) {
            const kWhPerMonth = (watts / 1000) * 24 * 30;
            const cost = kWhPerMonth * price;
            container.innerHTML += `<p>Estimation mensuelle instantanée : ${cost.toFixed(2)} ${unit}</p>`;

            // 📊 Estimation mensuelle moyenne — juste après l'instantanée
            await fetchAverageMonthlyCost(container);
        }
    }

    // 🕒 Dernière coupure
    fetch("/api/last-ob")
        .then(res => res.json())
        .then(data => {
            if (data.last_ob) {
                const last = new Date(data.last_ob);
                const now = new Date();
                const diffMs = now - last;
                const diffMin = Math.floor(diffMs / 60000);
                const diffH = Math.floor(diffMin / 60);
                const diffD = Math.floor(diffH / 24);
                const h = diffH % 24;
                const m = diffMin % 60;

                const p = document.createElement("p");
                p.textContent = `Dernière coupure : il y a ${diffD}j ${h}h ${m}min`;
                container.appendChild(p);
            }
        });
}

async function fetchAverageMonthlyCost(container) {
    try {
        const res = await fetch("/api/avg-monthly-cost");
        if (!res.ok) return;
        const data = await res.json();

        if (data.kwh > 0) {
            container.innerHTML += `<p>Estimation mensuelle moyenne : ${data.cost.toFixed(2)} ${data.unit}</p>`;
        }
    } catch (e) {
        console.warn("Erreur moyenne mensuelle :", e);
    }
}

let consoChart = null;

async function renderConsoGraph() {
    const range = document.getElementById("range-selector").value;
    console.log("Plage sélectionnée :", range);

    const res = await fetch(`/api/conso?range=${range}`);
    const data = await res.json();

    const labels = data.map(d => {
        const t = new Date(d.timestamp);
        return `${t.getHours()}h${String(t.getMinutes()).padStart(2, '0')}`;
    });

    const values = data.map(d => d.watts);

    const ctx = document.getElementById("consoChart").getContext("2d");

    // 🔄 Détruire l'ancien graphe si présent
    if (consoChart) {
        consoChart.destroy();
    }

    // 📊 Créer le nouveau graphe
    consoChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [{
                label: "Puissance (W)",
                data: values,
                borderColor: "#0055aa",
                backgroundColor: "rgba(0,85,170,0.1)",
                fill: true,
                tension: 0.2
            }]
        },
        options: {
            scales: {
                x: { title: { display: true, text: "Heure" } },
                y: { title: { display: true, text: "Watts" }, beginAtZero: true }
            }
        }
    });
}

// 🖱️ Rafraîchir le graphe à chaque changement de plage
document.getElementById("range-selector").addEventListener("change", renderConsoGraph);

// 📥 Appel initial
renderConsoGraph();



async function loadSavedValues() {
    const res = await fetch("/api/value");
    const data = await res.json();
    document.getElementById("price-input").value = data.price_per_kwh;
    document.getElementById("unit-input").value = data.currency;
}

document.getElementById("save-button").addEventListener("click", async () => {
    const price = parseFloat(document.getElementById("price-input").value);
    const unit = document.getElementById("unit-input").value;

    const payload = {
        price_per_kwh: isNaN(price) ? 0.26 : price,
        currency: unit || "€"
    };

    await fetch("/api/save-value", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
});

function refreshAll() {
    fetchUPS();
}

loadSavedValues();
refreshAll();
setInterval(refreshAll, 5000);
