"use strict";

let explorerState = null;

function getExplorerDialog() {
    let dialog = document.getElementById("chart-explorer-dialog");
    if (dialog) return dialog;

    dialog = document.createElement("dialog");
    dialog.id = "chart-explorer-dialog";
    dialog.className = "chart-explorer-dialog";
    dialog.innerHTML = `
        <div class="chart-explorer-shell">
            <header class="chart-explorer-heading">
                <div><span class="chart-overline">CHART DETAILS</span><h2 id="chart-explorer-title"></h2><p id="chart-explorer-summary"></p></div>
                <button type="button" class="chart-explorer-close" aria-label="Close chart details">×</button>
            </header>
            <div class="chart-explorer-layout">
                <div class="chart-explorer-visual"><div id="chart-explorer-canvas"></div></div>
                <section class="chart-explorer-sections"><h3>Data sections</h3><div id="chart-explorer-list"></div></section>
            </div>
        </div>`;
    document.body.append(dialog);
    dialog.querySelector(".chart-explorer-close").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", event => {
        if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", restoreExplorerChart);
    return dialog;
}

function renderExplorerSections(sections, selectedIndex) {
    const list = document.getElementById("chart-explorer-list");
    const nodes = sections.map((section, index) => {
        const item = document.createElement("details");
        item.className = `chart-explorer-section${index === selectedIndex ? " selected" : ""}`;
        item.open = index === selectedIndex;

        const summary = document.createElement("summary");
        const name = document.createElement("span");
        name.textContent = section.title || `Section ${index + 1}`;
        const count = document.createElement("span");
        count.className = "chart-explorer-count";
        count.textContent = section.countLabel || `${section.products?.length || 0} products`;
        summary.append(name, count);
        item.append(summary);

        if (section.summary) {
            const description = document.createElement("p");
            description.className = "chart-explorer-description";
            description.textContent = section.summary;
            item.append(description);
        }

        const products = document.createElement("div");
        products.className = "chart-explorer-products";
        (section.products || []).forEach(product => {
            const row = document.createElement("article");
            row.className = "chart-explorer-product";
            const title = document.createElement("strong");
            title.textContent = product.product_name || "Unnamed product";
            row.append(title);

            const fields = [
                ["Price", product.price == null ? "Not listed" : `${product.currency || ""} ${product.price}`.trim()],
                ["Rating", product.rating == null ? "Not listed" : `${product.rating} / 5`],
                ["Availability", product.availability || "Not listed"],
                ["Category", product.category || "Not listed"]
            ];
            const metadata = document.createElement("p");
            metadata.textContent = fields.map(([label, value]) => `${label}: ${value}`).join(" · ");
            row.append(metadata);

            try {
                const url = new URL(product.product_link);
                if (["http:", "https:"].includes(url.protocol)) {
                    const link = document.createElement("a");
                    link.href = url.href;
                    link.target = "_blank";
                    link.rel = "noopener noreferrer";
                    link.textContent = "Open product page ↗";
                    row.append(link);
                }
            } catch (_error) {}

            products.append(row);
        });
        if (!section.products?.length) {
            const empty = document.createElement("p");
            empty.className = "chart-explorer-description";
            empty.textContent = section.emptyText || "No product rows are available for this section.";
            products.append(empty);
        }
        item.append(products);

        summary.addEventListener("click", () => window.setTimeout(() => selectExplorerSection(index), 0));
        return item;
    });
    list.replaceChildren(...nodes);
}

window.createPriceStatisticsSections = function(products, statistics, formatPrice) {
    const priced = (products || [])
        .map(product => ({product, price: Number(product.price)}))
        .filter(item => Number.isFinite(item.price))
        .sort((a, b) => a.price - b.price);
    const minimum = Number(statistics?.minimum_price);
    const maximum = Number(statistics?.maximum_price);
    const median = Math.floor((priced.length - 1) / 2);
    const medianProducts = priced.length
        ? [priced[median].product, ...(median !== Math.ceil((priced.length - 1) / 2) ? [priced[Math.ceil((priced.length - 1) / 2)].product] : [])]
        : [];
    const matches = value => priced.filter(item => Math.abs(item.price - value) < 1e-8).map(item => item.product);

    return [
        {
            title: "Minimum",
            summary: `Lowest price in the dataset: ${formatPrice(statistics?.minimum_price)}.`,
            products: Number.isFinite(minimum) ? matches(minimum) : [],
            emptyText: "No product prices are available for this statistic."
        },
        {
            title: "Median",
            summary: `Middle price after sorting all ${priced.length} valid prices: ${formatPrice(statistics?.median_price)}.`,
            countLabel: `${medianProducts.length} central ${medianProducts.length === 1 ? "product" : "products"}`,
            products: medianProducts,
            emptyText: "No product prices are available for this statistic."
        },
        {
            title: "Average",
            summary: `Mean price across all ${priced.length} valid product prices: ${formatPrice(statistics?.average_price)}.`,
            countLabel: `${priced.length} prices used`,
            products: [],
            emptyText: "Every valid product price contributes to this average; it does not represent one specific product."
        },
        {
            title: "Maximum",
            summary: `Highest price in the dataset: ${formatPrice(statistics?.maximum_price)}.`,
            products: Number.isFinite(maximum) ? matches(maximum) : [],
            emptyText: "No product prices are available for this statistic."
        }
    ];
};

function selectExplorerSection(index) {
    if (!explorerState) return;
    explorerState.selectedIndex = index;
    explorerState.chart.canvas.dataset.selectedSection = String(index);
    const dataset = explorerState.chart.data.datasets[0];
    if (explorerState.chart.config.type === "pie" || explorerState.chart.config.type === "doughnut") {
        dataset.offset = explorerState.sections.map((_, itemIndex) => itemIndex === index ? 20 : 0);
        explorerState.chart.setActiveElements([]);
    } else {
        explorerState.chart.setActiveElements([{datasetIndex: 0, index}]);
    }
    explorerState.chart.update("active");
    renderExplorerSections(explorerState.sections, index);
}

function restoreExplorerChart() {
    if (!explorerState) return;
    const {chart, parent, nextSibling} = explorerState;
    const canvas = chart.canvas;
    if (parent) parent.insertBefore(canvas, nextSibling?.parentNode === parent ? nextSibling : null);
    if (chart.config.type === "pie" || chart.config.type === "doughnut") chart.data.datasets[0].offset = 0;
    chart.setActiveElements([]);
    chart.update("none");
    chart.resize();
    explorerState = null;
}

window.openChartExplorer = function(chart, title, sections, selectedIndex = null) {
    if (!chart) return;
    const dialog = getExplorerDialog();

    if (explorerState && explorerState.chart !== chart) {
        dialog.close();
    }
    if (!explorerState) {
        const canvas = chart.canvas;
        explorerState = {
            chart,
            sections,
            selectedIndex,
            parent: canvas.parentNode,
            nextSibling: canvas.nextSibling
        };
        document.getElementById("chart-explorer-title").textContent = title;
        document.getElementById("chart-explorer-summary").textContent = "Select a section to highlight it and inspect its products.";
        document.getElementById("chart-explorer-canvas").append(canvas);
        if (!dialog.open) dialog.showModal();
    } else {
        explorerState.sections = sections;
    }

    if (selectedIndex === null) {
        explorerState.chart.setActiveElements([]);
        if (chart.config.type === "pie" || chart.config.type === "doughnut") chart.data.datasets[0].offset = 0;
        chart.update("none");
        renderExplorerSections(sections, null);
    } else {
        selectExplorerSection(selectedIndex);
    }
    requestAnimationFrame(() => chart.resize());
};
