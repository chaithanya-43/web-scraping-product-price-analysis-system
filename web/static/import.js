"use strict";

let importChart = null;
let importedData = null;

function setImportStatus(message, error = false) {
    const status = document.getElementById("import-status");
    status.textContent = message;
    status.className = `status-box${error ? " error" : ""}`;
    if (!message) status.classList.add("hidden");
}

function formatImportPrice(value, currency) {
    if (!Number.isFinite(Number(value))) return "—";
    return `${currency ? `${currency} ` : ""}${Number(value).toLocaleString(undefined, {maximumFractionDigits: 2})}`;
}

function priceBuckets(products) {
    const priced = products.filter(product => Number.isFinite(Number(product.price)));
    if (!priced.length) return [];
    const low = Math.min(...priced.map(product => Number(product.price)));
    const high = Math.max(...priced.map(product => Number(product.price)));
    if (low === high) return [{label: formatImportPrice(low), products: priced}];
    const count = Math.min(6, Math.max(3, Math.ceil(Math.sqrt(priced.length))));
    const width = (high - low) / count;
    const buckets = Array.from({length: count}, (_, index) => {
        const start = low + index * width;
        const end = index === count - 1 ? high : start + width;
        return {start, end, products: []};
    });
    priced.forEach(product => {
        const index = Math.min(count - 1, Math.floor((Number(product.price) - low) / width));
        buckets[index].products.push(product);
    });
    return buckets.map(bucket => ({
        label: `${formatImportPrice(bucket.start)} – ${formatImportPrice(bucket.end)}`,
        products: bucket.products
    }));
}

function renderImportResults(data) {
    importedData = data;
    const products = data.products || [];
    const stats = data.statistics || {};
    const currency = data.currency || "";
    document.getElementById("result-title").textContent = data.source_name || "Imported products";
    document.getElementById("result-count").textContent = `${products.length} products`;
    document.getElementById("table-count").textContent = `${products.length} rows`;
    document.getElementById("import-results").classList.remove("hidden");

    const metrics = [
        ["Products", products.length],
        ["Minimum", formatImportPrice(stats.minimum_price, currency)],
        ["Maximum", formatImportPrice(stats.maximum_price, currency)],
        ["Average", formatImportPrice(stats.average_price, currency)],
        ["Median", formatImportPrice(stats.median_price, currency)]
    ];
    document.getElementById("import-metrics").replaceChildren(...metrics.map(([label, value]) => {
        const card = document.createElement("article");
        card.className = "surface import-metric";
        const title = document.createElement("span");
        title.textContent = label;
        const number = document.createElement("strong");
        number.textContent = value;
        card.append(title, number);
        return card;
    }));

    const buckets = priceBuckets(products);
    if (importChart) importChart.destroy();
    if (buckets.length && typeof Chart !== "undefined") {
        importChart = new Chart(document.getElementById("import-price-chart"), {
            type: "pie",
            data: {
                labels: buckets.map(bucket => bucket.label),
                datasets: [{
                    data: buckets.map(bucket => bucket.products.length),
                    backgroundColor: ["#22d3ee", "#6366f1", "#f97316", "#34d399", "#fbbf24", "#ec4899"],
                    borderColor: "#151920",
                    borderWidth: 2,
                    hoverOffset: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {duration: 700, easing: "easeOutQuart"},
                radius: "78%",
                plugins: {
                    legend: {display: true, position: "bottom", labels: {color: "#A7AFBD", boxWidth: 12, padding: 14}},
                    tooltip: {callbacks: {label: context => `${context.label}: ${context.raw} products`}}
                },
                onClick: (_event, elements) => {
                    const sections = buckets.map(bucket => ({
                        title: bucket.label,
                        summary: `${bucket.products.length} products in this range`,
                        products: bucket.products
                    }));
                    window.openChartExplorer(importChart, "Imported price ranges", sections, elements.length ? elements[0].index : null);
                }
            }
        });
    }

    renderImportProducts(products);
}

function renderImportProducts(products) {
    const rows = products.map(product => {
        const row = document.createElement("tr");
        const nameCell = document.createElement("td");
        nameCell.textContent = product.product_name || "Unnamed product";
        row.append(nameCell);
        [formatImportPrice(product.price, product.currency || importedData.currency || ""), product.currency || importedData.currency || "—", product.rating ?? "—", product.availability || "—"].forEach(value => {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.append(cell);
        });
        return row;
    });
    document.getElementById("import-products").replaceChildren(...rows);
}

document.getElementById("import-form").addEventListener("submit", async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = document.getElementById("import-button");
    button.disabled = true;
    button.querySelector("span").textContent = "Importing…";
    setImportStatus("Cleaning and analyzing the file…");
    try {
        const response = await fetch("/api/import", {method: "POST", body: new FormData(form)});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "The file could not be imported.");
        renderImportResults(data);
        const report = data.cleaning_report || {};
        const removed = (report.duplicates_removed || 0) + (report.invalid_prices_removed || 0);
        setImportStatus(`Analysis complete. ${data.products.length} products are ready.${removed ? ` ${removed} duplicate or invalid-price rows were removed.` : ""}`);
    } catch (error) {
        setImportStatus(error.message || "The file could not be imported.", true);
    } finally {
        button.disabled = false;
        button.querySelector("span").textContent = "Import and analyze";
    }
});

fetch("/api/auth/profile").then(response => {
    if (!response.ok) return window.location.assign("/login");
    return response.json();
}).then(data => {
    if (!data?.user) return;
    const first = data.user.name.trim().split(/\s+/)[0] || "U";
    document.getElementById("sidebar-user-name").textContent = data.user.name;
    document.getElementById("sidebar-user-email").textContent = data.user.email;
    document.getElementById("user-avatar").textContent = first[0].toUpperCase();
    document.getElementById("header-avatar").textContent = first[0].toUpperCase();
}).catch(() => window.location.assign("/login"));

document.getElementById("logout-button").addEventListener("click", async () => {
    await fetch("/api/auth/logout", {method: "POST"});
    window.location.assign("/login");
});

document.getElementById("sidebar-toggle").addEventListener("click", () => {
    const open = document.body.classList.toggle("sidebar-open");
    document.getElementById("sidebar-toggle").setAttribute("aria-expanded", String(open));
});
document.getElementById("sidebar-scrim").addEventListener("click", () => document.body.classList.remove("sidebar-open"));
