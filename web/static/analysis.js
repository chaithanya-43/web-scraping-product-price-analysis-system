"use strict";

let analysisData = null;
let analysisChart = null;

const PAGE_SIZE = 10;

let productPage = 1;
let filteredProducts = [];

const currencySymbols = {
    USD: "$",
    EUR: "€",
    GBP: "£",
    INR: "₹",
    JPY: "¥",
    CNY: "¥",
    CAD: "CA$",
    AUD: "A$"
};


function getAnalysisId() {
    const pathParts = window.location.pathname.split("/").filter(Boolean);

    const analysisIndex = pathParts.indexOf("analysis");

    if (analysisIndex !== -1 && pathParts[analysisIndex + 1]) {
        return pathParts[analysisIndex + 1];
    }

    return new URLSearchParams(window.location.search).get("analysis");
}


function getPageType() {
    const path = window.location.pathname;

    if (path.includes("price-comparison")) {
        return "price";
    }

    if (path.includes("price-distribution")) {
        return "distribution";
    }

    if (path.includes("price-rating")) {
        return "rating";
    }

    if (path.includes("price-statistics")) {
        return "statistics";
    }

    if (path.includes("products")) {
        return "products";
    }

    return "unknown";
}


function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function formatCurrency(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
        return "—";
    }

    const number = Number(value);
    const currency = analysisData?.currency || "";

    const symbol = currencySymbols[currency] || currency;

    return `${symbol ? symbol + " " : ""}${number.toLocaleString("en-IN", {
        maximumFractionDigits: 2
    })}`;
}


function shortName(value, length = 38) {
    const text = String(value || "Unnamed product");

    if (text.length <= length) {
        return text;
    }

    return `${text.slice(0, length - 1)}…`;
}


function setStatus(message, type = "") {
    const element = document.getElementById("analysis-status");

    if (!element) {
        return;
    }

    element.textContent = message;
    element.className = `analysis-status ${type}`.trim();

    if (!message) {
        element.classList.add("hidden");
    }
}


async function loadAnalysis() {
    const analysisId = getAnalysisId();

    if (!analysisId) {
        setStatus("No analysis was selected.", "error");
        return;
    }

    setStatus("Restoring saved analysis...");

    try {
        const response = await fetch(
            `/api/history/${encodeURIComponent(analysisId)}`
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Saved analysis could not be opened."
            );
        }

        // Save the successfully loaded analysis ID.
        if (data.analysis_id) {
            localStorage.setItem(
                "pricelens_active_analysis",
                String(data.analysis_id)
            );
        }

        analysisData = data;

        renderSharedInformation();

        const pageType = getPageType();

        if (pageType === "price") {
            renderPriceComparison();
        } else if (pageType === "distribution") {
            renderDistribution();
        } else if (pageType === "rating") {
            renderRating();
        } else if (pageType === "statistics") {
            renderStatistics();
        } else if (pageType === "products") {
            renderProducts();
        }

        setStatus("");

    } catch (error) {
        console.error("Failed to load saved analysis:", error);

        setStatus(
            error.message || "The saved analysis could not be loaded.",
            "error"
        );
    }
}


function renderSharedInformation() {
    const source = document.getElementById("analysis-source");
    const count = document.getElementById("analysis-product-count");

    if (source) {
        source.textContent = analysisData.source_name || "Unknown source";
    }

    if (count) {
        count.textContent = `${analysisData.products?.length || 0} products`;
    }

    const productsLink = document.getElementById("products-link");

    if (productsLink) {
        productsLink.href =
            `/analysis/${encodeURIComponent(analysisData.analysis_id)}/products`;
    }

    const productsTitle = document.getElementById("products-title");

    if (productsTitle) {
        productsTitle.textContent =
            `Collected products (${analysisData.products?.length || 0})`;
    }

    const minimum = document.getElementById("lowest-price");
    const maximum = document.getElementById("highest-price");
    const average = document.getElementById("average-price");

    if (minimum) {
        minimum.textContent =
            formatCurrency(analysisData.statistics?.minimum_price);
    }

    if (maximum) {
        maximum.textContent =
            formatCurrency(analysisData.statistics?.maximum_price);
    }

    if (average) {
        average.textContent =
            formatCurrency(analysisData.statistics?.average_price);
    }

    const statMap = {
        "stat-minimum": "minimum_price",
        "stat-median": "median_price",
        "stat-average": "average_price",
        "stat-maximum": "maximum_price"
    };

    Object.entries(statMap).forEach(([id, key]) => {
        const element = document.getElementById(id);

        if (element) {
            element.textContent =
                formatCurrency(analysisData.statistics?.[key]);
        }
    });
}


function getPricedProducts() {
    return (analysisData?.products || [])
        .map((product, index) => ({
            product,
            index,
            price: Number(product.price)
        }))
        .filter(item => Number.isFinite(item.price));
}


function destroyChart() {
    if (analysisChart) {
        analysisChart.destroy();
        analysisChart = null;
    }
}


function chartOptions() {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700, easing: "easeOutQuart" },

        plugins: {
            legend: {
                display: false
            },

            tooltip: {
                backgroundColor: "#151920",
                borderColor: "#343944",
                borderWidth: 1,
                titleColor: "#F8FAFC",
                bodyColor: "#C4C9D2",
                padding: 12
            }
        },

        scales: {
            x: {
                ticks: {
                    color: "#CBD5E1"
                },

                grid: {
                    color: "rgba(255,255,255,.055)"
                }
            },

            y: {
                ticks: {
                    color: "#CBD5E1"
                },

                grid: {
                    color: "rgba(255,255,255,.055)"
                }
            }
        }
    };
}


function renderPriceComparison() {
    destroyChart();

    const canvas = document.getElementById("analysis-chart");

    if (!canvas || typeof Chart === "undefined") {
        setStatus("The chart library could not be loaded.", "error");
        return;
    }

    const products = getPricedProducts()
        .sort((a, b) => a.price - b.price);

    const labels = products.map(item =>
        shortName(item.product.product_name)
    );

    const values = products.map(item => item.price);

    analysisChart = new Chart(canvas, {
        type: "bar",

        data: {
            labels,

            datasets: [{
                data: values,

                backgroundColor: "rgba(249,115,22,.78)",
                hoverBackgroundColor: "#fb923c",

                borderColor: "#f97316",
                borderWidth: 1,

                borderRadius: 6,
                borderSkipped: false
            }]
        },

        options: {
            ...chartOptions(),

            indexAxis: "y",

            scales: {
                x: {
                    ...chartOptions().scales.x,

                    beginAtZero: true,

                    title: {
                        display: true,
                        text: `Price ${currencySymbols[analysisData.currency] || analysisData.currency || ""}`,
                        color: "#A7AFBD"
                    }
                },

                y: {
                    ...chartOptions().scales.y,

                    grid: {
                        display: false
                    }
                }
            },

            onClick(event, elements) {
                const sections = products.map(item => ({
                    title: item.product.product_name || "Unnamed product",
                    products: [item.product]
                }));
                window.openChartExplorer(analysisChart, "Price comparison", sections, elements.length ? elements[0].index : null);
            }
        }
    });
}


function createPriceBuckets(products) {
    if (!products.length) {
        return [];
    }

    const prices = products.map(product => Number(product.price));

    const minimum = Math.min(...prices);
    const maximum = Math.max(...prices);

    if (minimum === maximum) {
        return [{
            low: minimum,
            high: maximum,
            products
        }];
    }

    const bucketCount = Math.min(6, Math.max(3, Math.ceil(Math.sqrt(products.length))));
    const width = (maximum - minimum) / bucketCount;

    const buckets = Array.from(
        { length: bucketCount },
        (_, index) => ({
            low: minimum + index * width,
            high: index === bucketCount - 1
                ? maximum
                : minimum + (index + 1) * width,
            products: []
        })
    );

    products.forEach(product => {
        const price = Number(product.price);

        let index = Math.floor((price - minimum) / width);

        if (index >= bucketCount) {
            index = bucketCount - 1;
        }

        buckets[index].products.push(product);
    });

    return buckets;
}


function renderDistribution() {
    destroyChart();

    const canvas = document.getElementById("analysis-chart");

    if (!canvas || typeof Chart === "undefined") {
        setStatus("The chart library could not be loaded.", "error");
        return;
    }

    const products = (analysisData.products || [])
        .filter(product => Number.isFinite(Number(product.price)));

    const buckets = createPriceBuckets(products);

    analysisChart = new Chart(canvas, {
        type: "pie",

        data: {
            labels: buckets.map(bucket =>
                `${formatCurrency(bucket.low)} – ${formatCurrency(bucket.high)}`
            ),

            datasets: [{
                data: buckets.map(bucket => bucket.products.length),

                backgroundColor: [
                    "#22d3ee", "#6366f1", "#f97316",
                    "#34d399", "#fbbf24", "#ec4899"
                ],
                hoverOffset: 8,
                borderColor: "#151920",
                borderWidth: 2
            }]
        },

        options: {
            ...chartOptions(),

            scales: {},
            radius: "78%",
            plugins: {
                ...chartOptions().plugins,
                legend: {
                    display: true,
                    position: "bottom",
                    labels: { color: "#A7AFBD", boxWidth: 12, padding: 14 }
                },
                tooltip: {
                    ...chartOptions().plugins.tooltip,
                    callbacks: {
                        label: context => `${context.label}: ${context.raw} products`
                    }
                }
            },

            onClick(event, elements) {
                const sections = buckets.map(bucket => ({
                    title: `${formatCurrency(bucket.low)} – ${formatCurrency(bucket.high)}`,
                    summary: `${bucket.products.length} products in this range`,
                    products: bucket.products
                }));
                window.openChartExplorer(analysisChart, "Price distribution", sections, elements.length ? elements[0].index : null);
            }
        }
    });
}


function renderRating() {
    destroyChart();

    const canvas = document.getElementById("analysis-chart");

    if (!canvas || typeof Chart === "undefined") {
        setStatus("The chart library could not be loaded.", "error");
        return;
    }

    const ratedProducts = (analysisData.products || [])
        .map((product, index) => ({
            product,
            index,
            rating: Number(product.rating),
            price: Number(product.price)
        }))
        .filter(item =>
            Number.isFinite(item.rating) &&
            Number.isFinite(item.price)
        );

    analysisChart = new Chart(canvas, {
        type: "scatter",

        data: {
            datasets: [{
                data: ratedProducts.map(item => ({
                    x: item.rating,
                    y: item.price
                })),

                backgroundColor: "rgba(249,115,22,.82)",
                hoverBackgroundColor: "#fb923c",

                borderColor: "#fed7aa",
                borderWidth: 1,

                pointRadius: 6,
                pointHoverRadius: 9
            }]
        },

        options: {
            ...chartOptions(),

            scales: {
                x: {
                    ...chartOptions().scales.x,

                    title: {
                        display: true,
                        text: "Rating",
                        color: "#A7AFBD"
                    }
                },

                y: {
                    ...chartOptions().scales.y,

                    beginAtZero: true,

                    title: {
                        display: true,
                        text: "Price",
                        color: "#A7AFBD"
                    }
                }
            },

            plugins: {
                ...chartOptions().plugins,

                tooltip: {
                    ...chartOptions().plugins.tooltip,

                    callbacks: {
                        label(context) {
                            const item = ratedProducts[context.dataIndex];

                            return `${item.product.product_name} · Rating ${item.rating} · ${formatCurrency(item.price)}`;
                        }
                    }
                }
            },

            onClick(event, elements) {
                const sections = ratedProducts.map(item => ({
                    title: item.product.product_name || "Unnamed product",
                    products: [item.product]
                }));
                window.openChartExplorer(analysisChart, "Price vs. rating", sections, elements.length ? elements[0].index : null);
            }
        }
    });
}


function renderStatistics() {
    destroyChart();

    const canvas = document.getElementById("analysis-chart");

    if (!canvas || typeof Chart === "undefined") {
        setStatus("The chart library could not be loaded.", "error");
        return;
    }

    const statistics = analysisData.statistics || {};

    analysisChart = new Chart(canvas, {
        type: "bar",

        data: {
            labels: [
                "Minimum",
                "Median",
                "Average",
                "Maximum"
            ],

            datasets: [{
                data: [
                    statistics.minimum_price,
                    statistics.median_price,
                    statistics.average_price,
                    statistics.maximum_price
                ],

                backgroundColor: [
                    "rgba(253,186,116,.55)",
                    "rgba(245,158,11,.65)",
                    "rgba(249,115,22,.78)",
                    "rgba(234,88,12,.9)"
                ],

                hoverBackgroundColor: [
                    "#fed7aa",
                    "#fbbf24",
                    "#fb923c",
                    "#f97316"
                ],

                borderWidth: 1,
                borderColor: "#f97316",

                borderRadius: 8,
                borderSkipped: false
            }]
        },

        options: {
            ...chartOptions(),

            scales: {
                x: {
                    ...chartOptions().scales.x,

                    grid: {
                        display: false
                    }
                },

                y: {
                    ...chartOptions().scales.y,

                    beginAtZero: true,

                    title: {
                        display: true,
                        text: "Price",
                        color: "#A7AFBD"
                    }
                }
            },
            onClick(_event, elements) {
                const sections = window.createPriceStatisticsSections(analysisData.products, statistics, formatCurrency);
                window.openChartExplorer(analysisChart, "Price statistics", sections, elements.length ? elements[0].index : null);
            }
        }
    });
}


function openProductDialog(product) {
    const dialog = document.getElementById("analysis-dialog");
    const content = document.getElementById("analysis-dialog-content");

    if (!dialog || !content) {
        return;
    }

    content.innerHTML = `
        <div class="dialog-inner">

            <button
                class="dialog-close"
                type="button"
                data-analysis-dialog-close
                aria-label="Close"
            >
                ×
            </button>

            <span class="chart-overline">PRODUCT</span>

            <h2>${escapeHtml(product.product_name || "Unnamed product")}</h2>

            <div class="dialog-product-price">
                ${formatCurrency(product.price)}
            </div>

            <div class="dialog-grid">

                <div>
                    <span>Rating</span>
                    <b>${escapeHtml(product.rating ?? "—")}</b>
                </div>

                <div>
                    <span>Availability</span>
                    <b>${escapeHtml(product.availability || "—")}</b>
                </div>

                <div>
                    <span>Category</span>
                    <b>${escapeHtml(product.category || "—")}</b>
                </div>

                <div>
                    <span>Website</span>
                    <b>${escapeHtml(product.website_name || analysisData.source_name || "—")}</b>
                </div>

            </div>

            ${
                product.product_link
                    ? `
                        <a
                            class="dialog-product-link"
                            href="${escapeHtml(product.product_link)}"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            Open product page ↗
                        </a>
                    `
                    : ""
            }

        </div>
    `;

    dialog.showModal();
}


function showBucketDialog(bucket) {
    const dialog = document.getElementById("analysis-dialog");
    const content = document.getElementById("analysis-dialog-content");

    if (!dialog || !content) {
        return;
    }

    content.innerHTML = `
        <div class="dialog-inner">

            <button
                class="dialog-close"
                type="button"
                data-analysis-dialog-close
                aria-label="Close"
            >
                ×
            </button>

            <span class="chart-overline">PRICE RANGE</span>

            <h2>
                ${formatCurrency(bucket.low)}
                –
                ${formatCurrency(bucket.high)}
            </h2>

            <p class="dialog-description">
                ${bucket.products.length} product${bucket.products.length === 1 ? "" : "s"}
                fall within this price range.
            </p>

            <div class="bucket-products">
                ${bucket.products.map(product => `
                    <button
                        type="button"
                        class="bucket-product"
                        data-product-name="${escapeHtml(product.product_name)}"
                    >
                        <span>
                            ${escapeHtml(shortName(product.product_name, 55))}
                        </span>

                        <b>${formatCurrency(product.price)}</b>
                    </button>
                `).join("")}
            </div>

        </div>
    `;

    dialog.showModal();
}


function renderProducts() {
    filteredProducts = [...(analysisData.products || [])];

    productPage = 1;

    renderProductTable();

    const search = document.getElementById("analysis-product-search");

    if (search) {
        search.addEventListener("input", applyProductFilters);
    }

    const sort = document.getElementById("analysis-product-sort");

    if (sort) {
        sort.addEventListener("change", applyProductFilters);
    }

    document.getElementById("analysis-page-prev")?.addEventListener(
        "click",
        () => {
            if (productPage > 1) {
                productPage--;
                renderProductTable();
            }
        }
    );

    document.getElementById("analysis-page-next")?.addEventListener(
        "click",
        () => {
            const totalPages = Math.max(
                1,
                Math.ceil(filteredProducts.length / PAGE_SIZE)
            );

            if (productPage < totalPages) {
                productPage++;
                renderProductTable();
            }
        }
    );
}


function applyProductFilters() {
    const search =
        document.getElementById("analysis-product-search")?.value
            .trim()
            .toLowerCase() || "";

    const sort =
        document.getElementById("analysis-product-sort")?.value || "name";

    filteredProducts = (analysisData.products || []).filter(product => {
        const text = [
            product.product_name,
            product.category,
            product.website_name
        ]
            .join(" ")
            .toLowerCase();

        return text.includes(search);
    });

    filteredProducts.sort((a, b) => {
        if (sort === "price-asc") {
            return Number(a.price || 0) - Number(b.price || 0);
        }

        if (sort === "price-desc") {
            return Number(b.price || 0) - Number(a.price || 0);
        }

        if (sort === "rating-desc") {
            return Number(b.rating || 0) - Number(a.rating || 0);
        }

        return String(a.product_name || "")
            .localeCompare(String(b.product_name || ""));
    });

    productPage = 1;

    renderProductTable();
}


function renderProductTable() {
    const table = document.getElementById("analysis-products-table");
    const empty = document.getElementById("analysis-products-empty");

    if (!table) {
        return;
    }

    const totalPages = Math.max(
        1,
        Math.ceil(filteredProducts.length / PAGE_SIZE)
    );

    if (productPage > totalPages) {
        productPage = totalPages;
    }

    const start = (productPage - 1) * PAGE_SIZE;

    const pageProducts = filteredProducts.slice(
        start,
        start + PAGE_SIZE
    );

    table.innerHTML = pageProducts.map(product => `
        <tr>

            <td>
                <div class="analysis-product-name">
                    ${escapeHtml(product.product_name || "Unnamed product")}
                </div>
            </td>

            <td class="analysis-product-price">
                ${formatCurrency(product.price)}
            </td>

            <td>
                ${escapeHtml(product.rating ?? "—")}
            </td>

            <td>
                ${escapeHtml(product.availability || "—")}
            </td>

            <td>
                ${escapeHtml(product.category || "—")}
            </td>

            <td>
                ${
                    product.product_link
                        ? `
                            <a
                                href="${escapeHtml(product.product_link)}"
                                target="_blank"
                                rel="noopener noreferrer"
                                class="product-link"
                            >
                                Open ↗
                            </a>
                        `
                        : "—"
                }
            </td>

        </tr>
    `).join("");

    empty?.classList.toggle(
        "hidden",
        filteredProducts.length !== 0
    );

    const range = document.getElementById("analysis-table-range");

    if (range) {
        const shownStart =
            filteredProducts.length ? start + 1 : 0;

        const shownEnd =
            Math.min(start + PAGE_SIZE, filteredProducts.length);

        range.textContent =
            `Showing ${shownStart}–${shownEnd} of ${filteredProducts.length}`;
    }

    const label = document.getElementById("analysis-page-label");

    if (label) {
        label.textContent = `${productPage} / ${totalPages}`;
    }

    const previous = document.getElementById("analysis-page-prev");
    const next = document.getElementById("analysis-page-next");

    if (previous) {
        previous.disabled = productPage <= 1;
    }

    if (next) {
        next.disabled = productPage >= totalPages;
    }
}


document.addEventListener("click", event => {

    const closeButton =
        event.target.closest("[data-analysis-dialog-close]");

    if (closeButton) {
        document.getElementById("analysis-dialog")?.close();
        return;
    }

    const bucketProduct =
        event.target.closest(".bucket-product");

    if (bucketProduct) {

        const name = bucketProduct.dataset.productName;

        const product = analysisData.products.find(
            item => item.product_name === name
        );

        if (product) {
            openProductDialog(product);
        }
    }
});


document.addEventListener("DOMContentLoaded", () => {

    const sidebar =
        document.getElementById("app-sidebar");

    const scrim =
        document.getElementById("sidebar-scrim");

    const toggle =
        document.getElementById("sidebar-toggle");

    if (toggle) {
        toggle.addEventListener("click", () => {

            const open =
                !sidebar.classList.contains("open");

            sidebar.classList.toggle("open", open);
            scrim.classList.toggle("visible", open);

            toggle.setAttribute(
                "aria-expanded",
                String(open)
            );
        });
    }

    if (scrim) {
        scrim.addEventListener("click", () => {

            sidebar.classList.remove("open");
            scrim.classList.remove("visible");

            toggle?.setAttribute(
                "aria-expanded",
                "false"
            );
        });
    }

    document
        .getElementById("logout-button")
        ?.addEventListener("click", async () => {

            await fetch("/api/auth/logout", {
                method: "POST"
            });

            window.location.assign("/login");
        });

    document
        .getElementById("analysis-dialog")
        ?.addEventListener("click", event => {

            if (event.target === event.currentTarget) {
                event.currentTarget.close();
            }
        });

    loadAnalysis();
});
