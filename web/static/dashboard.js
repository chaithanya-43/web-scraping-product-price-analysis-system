"use strict";


/* =========================================================
   GLOBAL STATE
========================================================= */

let analysis = null;
let activeCurrency = "";
let charts = {};
let selectedProductIndex = -1;
let tablePage = 1;

let priceChartPage = 1;
const priceChartPageSize = 10;

const pageSize = 8;

const currencySymbols = {
    GBP: "£",
    USD: "$",
    EUR: "€",
    INR: "₹"
};

const analysisTimeoutMs = 100_000;


/* =========================================================
   THEME
========================================================= */

function getTheme() {
    return localStorage.getItem("pricelens-theme") || "dark";
}


function applyTheme(theme) {
    const selectedTheme = theme === "light" ? "light" : "dark";

    document.documentElement.dataset.theme = selectedTheme;
    localStorage.setItem("pricelens-theme", selectedTheme);

    const button = document.getElementById("theme-toggle");

    if (button) {
        const icon = button.querySelector(".theme-icon");
        const label = button.querySelector(".theme-label");

        if (selectedTheme === "light") {
            if (icon) icon.textContent = "☾";
            if (label) label.textContent = "Dark";
            button.setAttribute("aria-label", "Switch to dark mode");
            button.setAttribute("title", "Switch to dark mode");
        } else {
            if (icon) icon.textContent = "☀";
            if (label) label.textContent = "Light";
            button.setAttribute("aria-label", "Switch to light mode");
            button.setAttribute("title", "Switch to light mode");
        }
    }

    if (analysis) {
        requestAnimationFrame(() => renderCharts());
    }
}


function initTheme() {
    const savedTheme = getTheme();

    applyTheme(savedTheme);

    const button = document.getElementById("theme-toggle");

    if (!button) return;

    button.addEventListener("click", () => {
        const current = document.documentElement.dataset.theme || "dark";
        applyTheme(current === "dark" ? "light" : "dark");
    });
}


function isLightTheme() {
    return document.documentElement.dataset.theme === "light";
}


function themeColors() {
    if (isLightTheme()) {
        return {
            text: "#334155",
            muted: "#64748b",
            grid: "rgba(100,116,139,.13)",
            tooltipBg: "#ffffff",
            tooltipBorder: "#dbe4ef",
            tooltipTitle: "#0f172a",
            tooltipBody: "#475569",
            primary: "#2563eb",
            primaryHover: "#1d4ed8",
            violet: "#6366f1",
            violetLight: "#818cf8",
            cyan: "#0891b2",
            cyanLight: "#06b6d4",
            green: "#10b981"
        };
    }

    return {
        text: "#d1d5db",
        muted: "#a1a1aa",
        grid: "rgba(168,165,181,.09)",
        tooltipBg: "#1c1b24",
        tooltipBorder: "#3c3948",
        tooltipTitle: "#e7f0fb",
        tooltipBody: "#b7c7da",
        primary: "#6366f1",
        primaryHover: "#818cf8",
        violet: "#a78bfa",
        violetLight: "#c4b5fd",
        cyan: "#22d3ee",
        cyanLight: "#67e8f9",
        green: "#34d399"
    };
}


/* =========================================================
   HELPERS
========================================================= */

function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = value ?? "";
    return node.innerHTML;
}


function formatMoney(value, currency = activeCurrency) {
    if (
        value === null ||
        value === undefined ||
        !Number.isFinite(Number(value))
    ) {
        return "—";
    }

    const prefix =
        currencySymbols[currency] ||
        (currency ? `${currency} ` : "");

    return `${prefix}${Number(value).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    })}`;
}


function validHttpUrl(value) {
    try {
        const url = new URL(value);

        return ["http:", "https:"].includes(url.protocol)
            ? url.href
            : null;

    } catch (_error) {
        return null;
    }
}


function setStatus(message, variant = "") {
    const element = document.getElementById("analysis-status");

    element.textContent = message;

    element.className =
        `status-box${variant ? ` ${variant}` : ""}`;
}


function shortName(value, length) {
    const name = String(value || "Product");

    return name.length > length
        ? `${name.slice(0, length - 1)}…`
        : name;
}


function formatCompact(value) {
    return `${currencySymbols[activeCurrency] || ""}${Number(value).toLocaleString(
        undefined,
        { maximumFractionDigits: 0 }
    )}`;
}


/* =========================================================
   USER
========================================================= */

async function loadUser() {
    try {
        const response = await fetch("/api/auth/profile");

        if (!response.ok) {
            window.location.assign("/login");
            return;
        }

        const { user } = await response.json();

        const firstName =
            user.name.trim().split(/\s+/)[0] || "there";

        document.getElementById("sidebar-user-name").textContent =
            user.name;

        document.getElementById("sidebar-user-email").textContent =
            user.email;

        document.getElementById("user-avatar").textContent =
            firstName[0].toUpperCase();

        document.getElementById("header-avatar").textContent =
            firstName[0].toUpperCase();

    } catch (_error) {
        window.location.assign("/login");
    }
}


/* =========================================================
   SOURCE DETECTION
========================================================= */

function detectSource(rawUrl) {
    const state = document.querySelector(".detection-state");
    const text = document.querySelector(".source-detection small");

    const url = validHttpUrl(rawUrl);

    if (!url) {
        state.textContent = "Waiting";
        state.classList.remove("detected");

        text.textContent =
            "Enter a URL to identify the website before analysis.";

        return;
    }

    const host = new URL(url)
        .hostname
        .replace(/^www\./, "");

    const known = {
        "books.toscrape.com": "Books to Scrape",
        "testingurl.dev": "TestingURL.dev",
        "myntra.com": "Myntra",
        "flipkart.com": "Flipkart",
        "amazon.com": "Amazon",
        "amazon.in": "Amazon India"
    };

    const source =
        Object.entries(known).find(
            ([domain]) =>
                host === domain ||
                host.endsWith(`.${domain}`)
        )?.[1] || host;

    state.textContent = "Detected";
    state.classList.add("detected");

    text.textContent =
        `${source} · generic structured data and page layouts`;
}


/* =========================================================
   PROGRESS
========================================================= */

function beginProgress(url, pages) {
    const wrap = document.getElementById("progress-wrap");

    wrap.classList.remove("hidden");

    const message =
        document.getElementById("progress-message");

    const bar =
        document.getElementById("progress-bar");

    const percent =
        document.getElementById("progress-percent");

    const labels =
        [...document.querySelectorAll(".progress-steps span")];

    const host =
        validHttpUrl(url)
            ? new URL(url).hostname.replace(/^www\./, "")
            : "the page";

    message.textContent =
        `Checking access and analyzing ${host} · up to ${pages} pages…`;

    percent.textContent = "In progress";

    bar.style.width = "";
    bar.classList.add("indeterminate");

    document.getElementById("analysis-ready-label").textContent =
        `Analyzing ${host}`;

    document
        .getElementById("analysis-ready-dot")
        .classList.add("working");

    labels.forEach(label =>
        label.classList.remove("current", "complete")
    );

    return succeeded => {
        bar.classList.remove("indeterminate");

        if (succeeded) {
            message.textContent = "Analysis ready";
            percent.textContent = "Complete";
            bar.style.width = "100%";

            labels.forEach(label =>
                label.classList.add("complete")
            );
        } else {
            message.textContent = "Analysis stopped";
            percent.textContent = "Stopped";
            bar.style.width = "0";
        }

        window.setTimeout(
            () => wrap.classList.add("hidden"),
            succeeded ? 850 : 1500
        );
    };
}

/* =========================================================
   ANALYSIS
========================================================= */

async function analyzeUrl(url, pages) {
    const button =
        document.getElementById("analyze-button");

    button.disabled = true;

    button.querySelector("span:first-child").textContent =
        "Analyzing…";

    document
        .getElementById("analysis-status")
        .classList.add("hidden");

    const finishProgress = beginProgress(url, pages);

    let succeeded = false;

    const controller = new AbortController();

    const timeoutId = window.setTimeout(
        () => controller.abort(),
        analysisTimeoutMs
    );

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                url,
                pages: Number(pages)
            }),
            signal: controller.signal
        });

        const data = await response.json();

        if (!response.ok) {
            const error = new Error(
                data.error ||
                "Analysis could not be completed."
            );

            error.status =
                data.status ||
                (response.status === 403
                    ? "RESTRICTED"
                    : "FAILED");

            throw error;
        }

        displayResults(data);

        succeeded = true;

        const pageSummary = Number.isInteger(data.pages_scraped)
            ? ` Scraped ${data.pages_scraped} of ${data.pages_requested} requested pages.`
            : "";
        const pageRows = Array.isArray(data.page_product_counts) && data.page_product_counts.length
            ? ` Rows found per page: ${data.page_product_counts.join(", ")}.`
            : "";
        const cleaning = data.cleaning_report || {};
        const cleanupSummary = cleaning.duplicates_removed || cleaning.invalid_prices_removed
            ? ` Cleaning removed ${cleaning.duplicates_removed || 0} duplicate rows and ${cleaning.invalid_prices_removed || 0} rows with missing or invalid prices.`
            : "";
        const message = data.currency_warning
            ? `Analysis ${data.status.toLowerCase()}.${pageSummary}${pageRows}${cleanupSummary} Currency mix detected; combined charts and price insights are hidden.`
            : `Analysis ${data.status.toLowerCase()} · ${data.products.length} products prepared from ${data.source_name}.${pageSummary}${pageRows}${cleanupSummary}`;

        setStatus(
            message,
            data.status === "PARTIAL"
                ? "warning"
                : ""
        );

    } catch (error) {

        const message =
            error.name === "AbortError"
                ? "Analysis took too long and was cancelled. Try fewer pages or another public URL."
                : error.message ||
                  "Analysis could not be completed.";

        setStatus(
            message,
            error.status === "RESTRICTED"
                ? "warning"
                : "error"
        );

        if (error.status) {
            const badge =
                document.getElementById("result-status");

            badge.textContent = error.status;

            badge.className =
                `result-badge ${error.status.toLowerCase()}`;
        }

    } finally {

        window.clearTimeout(timeoutId);

        finishProgress(succeeded);

        button.disabled = false;

        button.querySelector("span:first-child").textContent =
            "Analyze prices";

        document.getElementById(
            "analysis-ready-label"
        ).textContent = "Ready for analysis";

        document
            .getElementById("analysis-ready-dot")
            .classList.remove("working");
    }
}


/* =========================================================
   METRIC ANIMATION
========================================================= */

function animateMetric(element, value, formatter) {
    if (
        value === null ||
        value === undefined ||
        !Number.isFinite(Number(value))
    ) {
        element.textContent = "—";
        return;
    }

    const target = Number(value);
    const started = performance.now();
    const duration = 520;

    const frame = now => {
        const progress =
            Math.min(
                (now - started) / duration,
                1
            );

        const eased =
            1 - Math.pow(1 - progress, 3);

        element.textContent =
            formatter(target * eased);

        if (progress < 1) {
            requestAnimationFrame(frame);
        }
    };

    requestAnimationFrame(frame);
}


/* =========================================================
   DISPLAY RESULTS
========================================================= */

function displayResults(data) {
    analysis = data;

    if (data.analysis_id) {
        localStorage.setItem(
            "pricelens_active_analysis",
            String(data.analysis_id)
        );
    }

    activeCurrency = data.currency || "";

    document
        .getElementById("results-section")
        .classList.remove("hidden");

    const status =
        document.getElementById("result-status");

    status.textContent =
        data.status || "SUCCESS";

    status.className =
        `result-badge ${(data.status || "SUCCESS").toLowerCase()}`;

    document.getElementById("result-source").textContent =
        data.source_name || "Unknown source";

    document.getElementById("result-url").textContent =
        data.source_url ||
        document.getElementById("url").value;

    document.getElementById("product-count").textContent =
        data.products.length.toLocaleString();

    document.getElementById("stat-products").textContent =
        data.products.length.toLocaleString();

    document.getElementById("result-currency").textContent =
        data.currencies?.join(" · ") ||
        data.currency ||
        "Not specified";

    const analyzedDate =
        new Date(data.analyzed_at || Date.now());

    document.getElementById("result-time").textContent =
        analyzedDate.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit"
        });

    document.getElementById("result-date").textContent =
        analyzedDate.toLocaleDateString([], {
            day: "2-digit",
            month: "short",
            year: "numeric"
        });


    const statistics = data.statistics || {};

    const metrics = [
        ["minimum-price", "minimum_price"],
        ["maximum-price", "maximum_price"],
        ["average-price", "average_price"],
        ["median-price", "median_price"],
        ["price-difference", "price_difference"]
    ];

    metrics.forEach(([id, key]) => {
        const element = document.getElementById(id);

        animateMetric(
            element,
            statistics[key],
            value => formatMoney(value)
        );
    });


    document
        .getElementById("currency-warning")
        .classList.toggle(
            "hidden",
            !data.currency_warning
        );


    const insights = data.insights || {};

    document.getElementById(
        "lowest-priced-name"
    ).textContent =
        insights.lowest_priced_product?.product_name ||
        "—";

    document.getElementById(
        "lowest-priced"
    ).textContent =
        insights.lowest_priced_product
            ? formatMoney(
                  insights.lowest_priced_product.price
              )
            : "";


    document.getElementById(
        "highest-rated-name"
    ).textContent =
        insights.highest_rated_product?.product_name ||
        "No rating listed";

    document.getElementById(
        "highest-rated"
    ).textContent =
        insights.highest_rated_product
            ? `${Number(
                  insights.highest_rated_product.rating
              ).toFixed(1)} / 5`
            : "";


    document.getElementById(
        "most-expensive-name"
    ).textContent =
        insights.most_expensive_product?.product_name ||
        "—";

    document.getElementById(
        "most-expensive"
    ).textContent =
        insights.most_expensive_product
            ? formatMoney(
                  insights.most_expensive_product.price
              )
            : "";


    // Reset both pagination systems for a new analysis.
    tablePage = 1;
    priceChartPage = 1;

    renderProductTable();
    renderCharts();

    document
        .getElementById("results-section")
        .scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
}

/* =========================================================
   PRODUCT TABLE
========================================================= */

function filteredProducts() {
    const query =
        document
            .getElementById("product-search")
            .value
            .trim()
            .toLowerCase();

    const category =
        document.getElementById("category-filter").value;

    const sort =
        document.getElementById("product-sort").value;

    const products =
        (analysis?.products || [])
            .map((product, index) => ({
                product,
                index
            }))
            .filter(({ product }) => {

                const matchesQuery =
                    !query ||
                    [
                        product.product_name,
                        product.category,
                        product.website_name
                    ].some(value =>
                        String(value || "")
                            .toLowerCase()
                            .includes(query)
                    );

                return (
                    matchesQuery &&
                    (
                        !category ||
                        (product.category || "Other") === category
                    )
                );
            });


    products.sort((a, b) => {

        if (sort === "price-asc") {
            return (
                Number(a.product.price) -
                Number(b.product.price)
            );
        }

        if (sort === "price-desc") {
            return (
                Number(b.product.price) -
                Number(a.product.price)
            );
        }

        if (sort === "rating-desc") {
            return (
                Number(b.product.rating || -1) -
                Number(a.product.rating || -1)
            );
        }

        return String(
            a.product.product_name
        ).localeCompare(
            String(b.product.product_name)
        );
    });

    return products;
}


function renderProductTable() {
    if (!analysis) return;

    const category =
        document.getElementById("category-filter");

    const selected = category.value;

    const categories = [
        ...new Set(
            analysis.products.map(
                product => product.category || "Other"
            )
        )
    ].sort();

    category.innerHTML =
        `<option value="">All categories</option>` +
        categories
            .map(
                value =>
                    `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`
            )
            .join("");

    category.value =
        categories.includes(selected)
            ? selected
            : "";


    const matches = filteredProducts();

    const totalPages =
        Math.max(
            1,
            Math.ceil(matches.length / pageSize)
        );

    tablePage =
        Math.min(Math.max(1, tablePage), totalPages);

    const start =
        (tablePage - 1) * pageSize;

    const visible =
        matches.slice(
            start,
            start + pageSize
        );

    const table =
        document.getElementById("products-table");


    table.innerHTML =
        visible
            .map(({ product, index }) => {

                const url =
                    validHttpUrl(product.product_link);

                const availability =
                    String(
                        product.availability ||
                        "Not listed"
                    );

                const available =
                    /in.?stock|available/i.test(
                        availability
                    );

                return `
                    <tr>

                        <td>
                            <button
                                class="product-name-button"
                                data-product-index="${index}"
                                title="Open product details"
                            >
                                ${escapeHtml(
                                    product.product_name ||
                                    "Unnamed product"
                                )}
                            </button>
                        </td>

                        <td class="price-cell">
                            ${formatMoney(
                                product.price,
                                product.currency
                            )}
                        </td>

                        <td>
                            ${
                                product.rating === null ||
                                product.rating === undefined
                                    ? "—"
                                    : `
                                        <span class="rating-pill">
                                            ★ ${escapeHtml(product.rating)}
                                        </span>
                                      `
                            }
                        </td>

                        <td>
                            <span
                                class="availability-pill ${
                                    available ? "available" : ""
                                }"
                            >
                                ${escapeHtml(availability)}
                            </span>
                        </td>

                        <td>
                            ${escapeHtml(
                                product.category || "—"
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                product.website_name ||
                                analysis.source_name ||
                                "—"
                            )}
                        </td>

                        <td>
                            ${
                                url
                                    ? `
                                        <a
                                            class="view-link"
                                            href="${escapeHtml(url)}"
                                            target="_blank"
                                            rel="noopener noreferrer"
                                        >
                                            Open ↗
                                        </a>
                                      `
                                    : "—"
                            }
                        </td>

                    </tr>
                `;
            })
            .join("");


    document.getElementById("table-count").textContent =
        String(matches.length);

    document.getElementById("table-range").textContent =
        matches.length
            ? `Showing ${start + 1}–${Math.min(
                  start + visible.length,
                  matches.length
              )} of ${matches.length} products`
            : "Showing 0 products";

    document.getElementById("page-label").textContent =
        `${tablePage} / ${totalPages}`;

    document.getElementById("page-prev").disabled =
        tablePage <= 1;

    document.getElementById("page-next").disabled =
        tablePage >= totalPages;

    document
        .getElementById("table-empty")
        .classList.toggle(
            "hidden",
            matches.length > 0
        );
}

/* =========================================================
   CHART OPTIONS
========================================================= */

function chartOptions(currency = activeCurrency) {

    const colors = themeColors();

    return {
        responsive: true,
        maintainAspectRatio: false,

        animation: {
            duration: 700,
            easing: "easeOutQuart"
        },

        interaction: {
            intersect: true,
            mode: "nearest"
        },

        plugins: {

            legend: {
                display: false
            },

            tooltip: {

                backgroundColor: colors.tooltipBg,
                borderColor: colors.tooltipBorder,
                borderWidth: 1,

                titleColor: colors.tooltipTitle,
                bodyColor: colors.tooltipBody,

                padding: 10,
                displayColors: false,

                titleFont: {
                    family: "DM Sans",
                    weight: "600",
                    size: 11
                },

                bodyFont: {
                    family: "DM Mono",
                    size: 10
                },

                callbacks: {

                    title: items => {

                        if (!items?.length) {
                            return "";
                        }

                        const item = items[0];

                        if (
                            item.chart &&
                            item.chart.data &&
                            item.chart.data.labels
                        ) {
                            return (
                                item.chart.data.labels[
                                    item.dataIndex
                                ] || ""
                            );
                        }

                        return "";
                    },

                    label: context => {

                        const value =
                            context.parsed?.y ??
                            context.parsed?.x ??
                            context.raw?.y ??
                            context.raw?.x ??
                            context.raw;

                        return typeof value === "number"
                            ? formatMoney(value, currency)
                            : String(value);
                    }
                }
            }
        },

        scales: {

            x: {
                grid: {
                    color: colors.grid,
                    drawTicks: false
                },

                border: {
                    display: false
                },

                ticks: {
                    color: colors.text,
                    font: {
                        family: "DM Sans",
                        size: 10
                    },
                    maxRotation: 0
                }
            },

            y: {
                grid: {
                    color: colors.grid,
                    drawTicks: false
                },

                border: {
                    display: false
                },

                ticks: {
                    color: colors.text,
                    font: {
                        family: "DM Sans",
                        size: 10
                    },
                    padding: 7
                }
            }
        },

        onHover: (event, active) => {

            if (event.native?.target) {
                event.native.target.style.cursor =
                    active.length
                        ? "pointer"
                        : "default";
            }
        }
    };
}


/* =========================================================
   CHARTS
========================================================= */

function renderCharts() {

    Object.values(charts).forEach(chart =>
        chart?.destroy()
    );

    charts = {};

    const grid =
        document.getElementById("charts-grid");

    if (!analysis) return;

    if (analysis.currency_warning) {
        grid.classList.add("hidden");
        return;
    }

    grid.classList.remove("hidden");


    if (typeof Chart === "undefined") {

        grid.classList.add("hidden");

        setStatus(
            "The analysis finished, but the chart library did not load. Product results are still available below.",
            "warning"
        );

        return;
    }


    const colors = themeColors();

    Chart.defaults.color = colors.text;

    const products =
        analysis.products;

    const indexed =
        products
            .map((product, index) => ({
                product,
                index
            }))
            .filter(item =>
                Number.isFinite(
                    Number(item.product.price)
                )
            );


    /* -----------------------------------------------------
       PRICE COMPARISON
    ----------------------------------------------------- */

    const byPrice = [...indexed].sort(
        (a, b) =>
            Number(a.product.price) -
            Number(b.product.price)
    );

    const priceChartTotalPages = Math.max(
        1,
        Math.ceil(byPrice.length / priceChartPageSize)
    );

    priceChartPage = Math.min(
        Math.max(1, priceChartPage),
        priceChartTotalPages
    );

    const chartStart =
        (priceChartPage - 1) * priceChartPageSize;

    const chartProducts = byPrice.slice(
        chartStart,
        chartStart + priceChartPageSize
    );


    charts.price = new Chart(
        document.getElementById("price-chart"),
        {
            type: "bar",

            data: {
                labels: chartProducts.map(
                    ({ product }) =>
                        shortName(product.product_name, 23)
                ),

                datasets: [
                    {
                        data: chartProducts.map(
                            ({ product }) => Number(product.price)
                        ),

                        backgroundColor: chartProducts.map(
                            ({ index }) =>
                                index === selectedProductIndex
                                    ? colors.violet
                                    : selectedProductIndex >= 0
                                        ? (
                                            isLightTheme()
                                                ? "rgba(37,99,235,.20)"
                                                : "rgba(99,102,241,.28)"
                                          )
                                        : (
                                            isLightTheme()
                                                ? "rgba(37,99,235,.78)"
                                                : "rgba(99,102,241,.82)"
                                          )
                        ),

                        hoverBackgroundColor: colors.violetLight,

                        borderColor: isLightTheme()
                            ? "rgba(37,99,235,.35)"
                            : "rgba(167,139,250,.42)",

                        borderWidth: 1,
                        borderRadius: 5,
                        borderSkipped: false
                    }
                ]
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
                            text: `Price ${
                                currencySymbols[activeCurrency] ||
                                activeCurrency ||
                                ""
                            }`,
                            color: colors.muted
                        }
                    },

                    y: {
                        ...chartOptions().scales.y,

                        grid: {
                            display: false
                        }
                    }
                },

                plugins: {
                    ...chartOptions().plugins,

                    tooltip: {
                        ...chartOptions().plugins.tooltip,

                        title: items => {
                            if (!items.length) return "";

                            return (
                                chartProducts[items[0].dataIndex]
                                    ?.product?.product_name || ""
                            );
                        },

                        label: context =>
                            formatMoney(
                                context.parsed.x ?? context.raw,
                                activeCurrency
                            )
                    }
                },

                onClick: (_event, elements) => {
                    const sections = chartProducts.map(({product}) => ({
                        title: product.product_name || "Unnamed product",
                        products: [product]
                    }));
                    window.openChartExplorer(charts.price, "Price comparison", sections, elements.length ? elements[0].index : null);
                }
            }
        }
    );


    /* -----------------------------------------------------
       PRICE CHART PAGINATION
    ----------------------------------------------------- */

    const priceCanvas =
        document.getElementById("price-chart");

    let pricePagination =
        document.getElementById("price-chart-pagination");

    if (!pricePagination) {
        pricePagination = document.createElement("div");

        pricePagination.id = "price-chart-pagination";
        pricePagination.className = "chart-pagination";

        const priceChartCard = priceCanvas.closest(".chart-card");
        if (priceChartCard) {
            priceChartCard.appendChild(pricePagination);
        }
    }

    pricePagination.innerHTML = `
        <button
            type="button"
            id="price-chart-prev"
            ${priceChartPage === 1 ? "disabled" : ""}
        >
            ← Previous
        </button>

        <span>
            Page ${priceChartPage} of ${priceChartTotalPages}
            · ${byPrice.length} products
        </span>

        <button
            type="button"
            id="price-chart-next"
            ${
                priceChartPage === priceChartTotalPages
                    ? "disabled"
                    : ""
            }
        >
            Next →
        </button>
    `;

    document.getElementById("price-chart-prev").onclick = () => {
        if (priceChartPage > 1) {
            priceChartPage--;
            renderCharts();
        }
    };

    document.getElementById("price-chart-next").onclick = () => {
        if (priceChartPage < priceChartTotalPages) {
            priceChartPage++;
            renderCharts();
        }
    };


    /* -----------------------------------------------------
       PRICE DISTRIBUTION
    ----------------------------------------------------- */

    const buckets =
        makeBuckets(
            indexed.map(
                item => item.product
            )
        );


    charts.distribution =
        new Chart(
            document.getElementById(
                "distribution-chart"
            ),
            {
                type: "pie",

                data: {

                    labels:
                        buckets.map(
                            bucket =>
                                `${formatCompact(
                                    bucket.low
                                )}–${formatCompact(
                                    bucket.high
                                )}`
                        ),

                    datasets: [
                        {

                            data:
                                buckets.map(
                                    bucket =>
                                        bucket.products.length
                                ),

                            backgroundColor: [
                                "#22d3ee", "#6366f1", "#f97316",
                                "#34d399", "#fbbf24", "#ec4899"
                            ],
                            hoverOffset: 8,
                            borderColor: isLightTheme() ? "#fff" : "#151920",
                            borderWidth: 2
                        }
                    ]
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
                            labels: { color: colors.text, boxWidth: 12, padding: 12 }
                        },
                        tooltip: {
                            ...chartOptions().plugins.tooltip,
                            callbacks: {
                                label: context => `${context.label}: ${context.raw} products`
                            }
                        }
                    },

                    onClick: (_event, elements) => {
                        const sections = buckets.map(bucket => ({
                            title: `${formatCompact(bucket.low)}–${formatCompact(bucket.high)}`,
                            summary: `${bucket.products.length} products in this range`,
                            products: bucket.products
                        }));
                        window.openChartExplorer(charts.distribution, "Price ranges", sections, elements.length ? elements[0].index : null);
                    }
                }
            }
        );


    /* -----------------------------------------------------
       RATING VS PRICE
    ----------------------------------------------------- */

    const rated =
        indexed
            .filter(({ product }) =>
                Number.isFinite(
                    Number(product.rating)
                )
            )
            .map(({ product, index }) => ({
                x: Number(product.rating),
                y: Number(product.price),
                index
            }));


    charts.rating =
        new Chart(
            document.getElementById(
                "rating-price-chart"
            ),
            {
                type: "scatter",

                data: {

                    datasets: [
                        {

                            data: rated,

                            pointRadius: 5,

                            pointHoverRadius: 8,

                            backgroundColor:
                                isLightTheme()
                                    ? "rgba(99,102,241,.72)"
                                    : "rgba(167,139,250,.82)",

                            hoverBackgroundColor:
                                colors.cyan,

                            borderColor:
                                colors.violetLight,

                            borderWidth: 1
                        }
                    ]
                },

                options: {

                    ...chartOptions(),

                    parsing: false,

                    scales: {

                        x: {
                            ...chartOptions().scales.x,

                            min: 0,
                            max: 5,

                            title: {
                                display: true,
                                text: "Rating / 5",
                                color: colors.muted
                            }
                        },

                        y: {
                            ...chartOptions().scales.y,

                            beginAtZero: true,

                            title: {
                                display: true,

                                text:
                                    `Price ${
                                        currencySymbols[
                                            activeCurrency
                                        ] ||
                                        activeCurrency ||
                                        ""
                                    }`,

                                color: colors.muted
                            }
                        }
                    },

                    plugins: {

                        ...chartOptions().plugins,

                        tooltip: {

                            ...chartOptions().plugins.tooltip,

                            callbacks: {

                                title: items => {

                                    if (!items.length) {
                                        return "";
                                    }

                                    const dataIndex =
                                        items[0].dataIndex;

                                    const productIndex =
                                        rated[
                                            dataIndex
                                        ]?.index;

                                    return products[
                                        productIndex
                                    ]?.product_name || "";
                                },

                                label: context =>
                                    `${formatMoney(
                                        context.parsed.y
                                    )} · ${
                                        context.parsed.x
                                    }/5`
                            }
                        }
                    },

                    onClick: (_event, elements) => {

                        const sections = rated.map(item => ({
                            title: products[item.index].product_name || "Unnamed product",
                            products: [products[item.index]]
                        }));
                        window.openChartExplorer(charts.rating, "Price vs. rating", sections, elements.length ? elements[0].index : null);
                    }
                }
            }
        );


    /* -----------------------------------------------------
       PRICE STATISTICS
    ----------------------------------------------------- */

    const stats =
        analysis.statistics || {};

    const metrics = [
        {
            label: "Minimum",
            value: stats.minimum_price,
            product:
                analysis.insights
                    ?.lowest_priced_product
        },

        {
            label: "Median",
            value: stats.median_price
        },

        {
            label: "Average",
            value: stats.average_price
        },

        {
            label: "Maximum",
            value: stats.maximum_price,
            product:
                analysis.insights
                    ?.most_expensive_product
        }
    ].filter(item =>
        Number.isFinite(
            Number(item.value)
        )
    );


    charts.stats =
        new Chart(
            document.getElementById(
                "stats-chart"
            ),
            {
                type: "bar",

                data: {

                    labels:
                        metrics.map(
                            metric => metric.label
                        ),

                    datasets: [
                        {

                            data:
                                metrics.map(
                                    metric =>
                                        Number(metric.value)
                                ),

                            backgroundColor:
                                isLightTheme()
                                    ? [
                                        "rgba(16,185,129,.72)",
                                        "rgba(99,102,241,.52)",
                                        "rgba(37,99,235,.72)",
                                        "rgba(8,145,178,.72)"
                                    ]
                                    : [
                                        "rgba(52,211,153,.82)",
                                        "rgba(167,139,250,.62)",
                                        "rgba(99,102,241,.8)",
                                        "rgba(34,211,238,.82)"
                                    ],

                            hoverBackgroundColor:
                                colors.violetLight,

                            borderRadius: 6,

                            borderSkipped: false
                        }
                    ]
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

                            beginAtZero: true
                        }
                    },

                    plugins: {

                        ...chartOptions().plugins,

                        tooltip: {

                            ...chartOptions().plugins.tooltip,

                            callbacks: {

                                title: items => {

                                    if (!items.length) {
                                        return "";
                                    }

                                    const item =
                                        byPrice[items[0].dataIndex];

                                    return (
                                        item?.product?.product_name ||
                                        "Product"
                                    );
                                },

                                label: context => {

                                    const item =
                                        byPrice[context.dataIndex];

                                    if (!item) {
                                        return "";
                                    }

                                    return `Price: ${formatMoney(
                                        item.product.price,
                                        item.product.currency || activeCurrency
                                    )}`;
                                }
                            }
                        }
                    },

                    onClick: (_event, elements) => {
                        const sections = window.createPriceStatisticsSections(analysis.products, analysis.statistics, formatMoney);
                        window.openChartExplorer(charts.stats, "Price statistics", sections, elements.length ? elements[0].index : null);
                    }
                }
            }
        );
}


/* =========================================================
   PRICE BUCKETS
========================================================= */

function makeBuckets(products) {

    if (!products.length) {
        return [];
    }

    const values =
        products.map(
            product =>
                Number(product.price)
        );

    const min =
        Math.min(...values);

    const max =
        Math.max(...values);

    const span =
        max - min;

    const step =
        span === 0
            ? 1
            : span / 5;


    const buckets =
        Array.from(
            {
                length:
                    span === 0
                        ? 1
                        : 5
            },
            (_, index) => ({
                low:
                    min + index * step,

                high:
                    index === 4
                        ? max + Number.EPSILON
                        : min +
                          (index + 1) * step,

                products: []
            })
        );


    products.forEach(product => {

        const index =
            span === 0
                ? 0
                : Math.min(
                    4,
                    Math.floor(
                        (
                            Number(product.price) -
                            min
                        ) / step
                    )
                );

        buckets[index]
            .products
            .push(product);
    });


    return buckets;
}


/* =========================================================
   PRODUCT DETAIL DIALOG
========================================================= */

function openProductDialog(product) {
        if (!product) {
        return;
    }

    const url =
        validHttpUrl(
            product.product_link
        );

    const fields = [

        [
            "RATING",
            product.rating === null ||
            product.rating === undefined
                ? "Not listed"
                : `${product.rating} / 5`
        ],

        [
            "AVAILABILITY",
            product.availability ||
            "Not listed"
        ],

        [
            "CATEGORY",
            product.category ||
            "Not listed"
        ],

        [
            "DISCOUNT",
            product.discount === null ||
            product.discount === undefined
                ? "Not listed"
                : `${product.discount}%`
        ],

        [
            "WEBSITE",
            product.website_name ||
            analysis?.source_name ||
            "Not listed"
        ],

        [
            "LAST UPDATED",
            product.last_updated
                ? new Date(
                      product.last_updated
                  ).toLocaleString()
                : "Not listed"
        ]
    ];


    document.getElementById(
        "detail-content"
    ).innerHTML = `

        <div class="dialog-inner">

            <div class="dialog-top">

                <div>

                    <span class="dialog-kicker">
                        PRODUCT DETAIL
                    </span>

                    <h2
                        class="dialog-title"
                        id="detail-title"
                    >
                        ${escapeHtml(
                            product.product_name ||
                            "Product"
                        )}
                    </h2>

                </div>

                <button
                    class="dialog-close"
                    data-dialog-close
                    aria-label="Close product details"
                >
                    ×
                </button>

            </div>


            <div class="dialog-price">

                <span>COLLECTED PRICE</span>

                <b>
                    ${formatMoney(
                        product.price,
                        product.currency
                    )}
                </b>

                <small>
                    ${escapeHtml(
                        product.currency ||
                        "Currency not specified"
                    )}
                </small>

            </div>


            <div class="detail-grid">

                ${fields
                    .map(
                        ([label, value]) =>
                            `
                            <div class="detail-field">

                                <span>
                                    ${escapeHtml(label)}
                                </span>

                                <b>
                                    ${escapeHtml(value)}
                                </b>

                            </div>
                            `
                    )
                    .join("")}

            </div>


            <div class="dialog-actions">

                <button
                    class="dialog-secondary"
                    data-dialog-close
                >
                    Close
                </button>

                ${
                    url
                        ? `
                            <a
                                class="dialog-primary"
                                href="${escapeHtml(url)}"
                                target="_blank"
                                rel="noopener noreferrer"
                            >
                                View product ↗
                            </a>
                          `
                        : ""
                }

            </div>

        </div>
    `;


    document
        .getElementById("detail-dialog")
        .showModal();
}


/* =========================================================
   DISTRIBUTION DIALOG
========================================================= */

function showBucketDialog(bucket) {

    const dialog =
        document.getElementById(
            "detail-dialog"
        );

    const content =
        document.getElementById(
            "detail-content"
        );


    content.innerHTML = `

        <div class="dialog-inner">

            <div class="dialog-top">

                <div>

                    <span class="dialog-kicker">
                        PRICE DISTRIBUTION ·
                        ${bucket.products.length}
                        PRODUCTS
                    </span>

                    <h2
                        class="dialog-title"
                        id="detail-title"
                    >
                        ${formatMoney(bucket.low)}
                        –
                        ${formatMoney(bucket.high)}
                    </h2>

                </div>

                <button
                    class="dialog-close"
                    data-dialog-close
                    aria-label="Close range details"
                >
                    ×
                </button>

            </div>


            <div class="drill-list">

                ${bucket.products
                    .map(product => {

                        const index =
                            analysis.products.indexOf(
                                product
                            );

                        const url =
                            validHttpUrl(
                                product.product_link
                            );

                        return `

                            <div class="drill-row">

                                <button
                                    class="drill-product"
                                    data-product-index="${index}"
                                >
                                    ${escapeHtml(
                                        product.product_name
                                    )}
                                </button>

                                <span class="drill-price">
                                    ${formatMoney(
                                        product.price,
                                        product.currency
                                    )}
                                </span>

                                <span class="drill-rating">
                                    ${
                                        product.rating == null
                                            ? "—"
                                            : `★ ${escapeHtml(
                                                  product.rating
                                              )}`
                                    }
                                </span>

                                ${
                                    url
                                        ? `
                                            <a
                                                href="${escapeHtml(url)}"
                                                target="_blank"
                                                rel="noopener noreferrer"
                                            >
                                                View ↗
                                            </a>
                                          `
                                        : ""
                                }

                            </div>
                        `;
                    })
                    .join("")}

            </div>

        </div>
    `;


    dialog.showModal();
}


/* =========================================================
   HISTORY
========================================================= */

async function loadHistoryAnalysis(id) {

    setStatus(
        "Restoring saved analysis…"
    );

    try {

        const response =
            await fetch(
                `/api/history/${encodeURIComponent(id)}`
            );

        const data =
            await response.json();

        if (!response.ok) {
            throw new Error(
                data.error ||
                "Saved analysis could not be opened."
            );
        }

        document.getElementById("url").value =
            data.source_url || "";
        document.getElementById("url").title = data.source_url || "";
        document.getElementById("clear-url").classList.toggle(
            "hidden",
            !data.source_url
        );

        detectSource(
            data.source_url || ""
        );

        displayResults(data);

        setStatus(
            `Saved analysis restored · ${data.products.length} products from ${data.source_name}.`
        );

    } catch (error) {

        setStatus(
            error.message,
            "error"
        );
    }
}


/* =========================================================
   CSV EXPORT
========================================================= */

function exportCsv() {
    exportAnalysis("csv");
}

function exportXlsx() {
    exportAnalysis("xlsx");
}

function exportAnalysis(format) {
    if (!analysis?.analysis_id) {
        setStatus("Save or import an analysis before exporting.", "error");
        return;
    }
    window.location.assign(`/api/history/${analysis.analysis_id}/export/${format}`);
}



/* =========================================================
   SIDEBAR
========================================================= */

function toggleSidebar() {

    const sidebar =
        document.getElementById(
            "app-sidebar"
        );

    const scrim =
        document.getElementById(
            "sidebar-scrim"
        );

    const toggle =
        document.getElementById(
            "sidebar-toggle"
        );


    const open =
        !sidebar.classList.contains(
            "open"
        );


    sidebar.classList.toggle(
        "open",
        open
    );

    scrim.classList.toggle(
        "visible",
        open
    );

    toggle.setAttribute(
        "aria-expanded",
        String(open)
    );
}


function closeSidebar() {

    document
        .getElementById(
            "app-sidebar"
        )
        .classList.remove(
            "open"
        );

    document
        .getElementById(
            "sidebar-scrim"
        )
        .classList.remove(
            "visible"
        );

    document
        .getElementById(
            "sidebar-toggle"
        )
        .setAttribute(
            "aria-expanded",
            "false"
        );
}


/* =========================================================
   DOM READY
========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    () => {

        /*
         * Initialize theme FIRST.
         */
        initTheme();

        loadUser();

        /* ---------------------------------------------
           URL input
        --------------------------------------------- */

        const form =
            document.getElementById(
                "analysis-form"
            );

        const urlInput =
            document.getElementById(
                "url"
            );


        urlInput.addEventListener(
            "input",
            () => {

                urlInput.title = urlInput.value;

                detectSource(
                    urlInput.value
                );

                document
                    .getElementById(
                        "clear-url"
                    )
                    .classList.toggle(
                        "hidden",
                        !urlInput.value
                    );
            }
        );


        document
            .getElementById(
                "clear-url"
            )
            .addEventListener(
                "click",
                () => {

                    urlInput.value = "";
                    urlInput.title = "";

                    urlInput.focus();

                    detectSource("");

                    document
                        .getElementById(
                            "clear-url"
                        )
                        .classList.add("hidden");
                }
            );


        /* ---------------------------------------------
           Sidebar Analyze
        --------------------------------------------- */

        document
            .querySelectorAll(
                '[data-scroll="analyze"]'
            )
            .forEach(link => {

                link.addEventListener(
                    "click",
                    event => {

                        event.preventDefault();

                        document
                            .getElementById(
                                "analyze"
                            )
                            .scrollIntoView({
                                behavior:
                                    "smooth"
                            });

                        closeSidebar();
                    }
                );
            });


        /* ---------------------------------------------
           Analysis form
        --------------------------------------------- */

        form.addEventListener(
            "submit",
            event => {

                event.preventDefault();

                const normalized =
                    validHttpUrl(
                        urlInput.value.trim()
                    );


                if (!normalized) {

                    setStatus(
                        "Please enter a valid product, search, or category URL.",
                        "error"
                    );

                    return;
                }


                analyzeUrl(
                    normalized,
                    document.getElementById(
                        "pages"
                    ).value
                );
            }
        );


        /* ---------------------------------------------
           Table
        --------------------------------------------- */

        document
            .getElementById(
                "product-search"
            )
            .addEventListener(
                "input",
                () => {

                    tablePage = 1;

                    renderProductTable();
                }
            );


        document
            .getElementById(
                "category-filter"
            )
            .addEventListener(
                "change",
                () => {

                    tablePage = 1;

                    renderProductTable();
                }
            );


        document
            .getElementById(
                "product-sort"
            )
            .addEventListener(
                "change",
                () => {

                    tablePage = 1;

                    renderProductTable();
                }
            );


        document
            .getElementById(
                "page-prev"
            )
            .addEventListener(
                "click",
                () => {

                    tablePage--;

                    renderProductTable();
                }
            );


        document
            .getElementById(
                "page-next"
            )
            .addEventListener(
                "click",
                () => {

                    tablePage++;

                    renderProductTable();
                }
            );


        /* ---------------------------------------------
           Product table dialog
        --------------------------------------------- */

        document
            .getElementById(
                "products-table"
            )
            .addEventListener(
                "click",
                event => {

                    const button =
                        event.target.closest(
                            "[data-product-index]"
                        );

                    if (!button) {
                        return;
                    }

                    openProductDialog(
                        analysis.products[
                            Number(
                                button.dataset
                                    .productIndex
                            )
                        ]
                    );
                }
            );


        /* ---------------------------------------------
           Detail dialog
        --------------------------------------------- */

        document
            .getElementById(
                "detail-content"
            )
            .addEventListener(
                "click",
                event => {

                    if (
                        event.target.closest(
                            "[data-dialog-close]"
                        )
                    ) {

                        document
                            .getElementById(
                                "detail-dialog"
                            )
                            .close();

                        return;
                    }


                    const button =
                        event.target.closest(
                            "[data-product-index]"
                        );

                    if (button) {

                        const index =
                            Number(
                                button.dataset
                                    .productIndex
                            );

                        document
                            .getElementById(
                                "detail-dialog"
                            )
                            .close();

                        openProductDialog(analysis.products[index]);
                    }
                }
            );


        document
            .getElementById(
                "detail-dialog"
            )
            .addEventListener(
                "click",
                event => {

                    if (
                        event.target ===
                        event.currentTarget
                    ) {
                        event.currentTarget.close();
                    }
                }
            );


        /* ---------------------------------------------
           Export
        --------------------------------------------- */

        document.getElementById("export-csv")?.addEventListener("click", exportCsv);
        document.getElementById("export-xlsx")?.addEventListener("click", exportXlsx);

        /* ---------------------------------------------
           Logout
        --------------------------------------------- */

        document
            .getElementById(
                "logout-button"
            )
            .addEventListener(
                "click",
                async () => {

                    await fetch(
                        "/api/auth/logout",
                        {
                            method: "POST"
                        }
                    );

                    window.location.assign(
                        "/login"
                    );
                }
            );


        /* ---------------------------------------------
           Mobile sidebar
        --------------------------------------------- */

        document
            .getElementById(
                "sidebar-toggle"
            )
            .addEventListener(
                "click",
                toggleSidebar
            );


        document
            .getElementById(
                "sidebar-scrim"
            )
            .addEventListener(
                "click",
                closeSidebar
            );


        /* ---------------------------------------------
           Restore history analysis
        --------------------------------------------- */

        const historyId =
            new URLSearchParams(
                window.location.search
            ).get("analysis");

        const activeAnalysisId =
            localStorage.getItem(
                "pricelens_active_analysis"
            );

        if (historyId) {
            loadHistoryAnalysis(historyId);
        } else if (activeAnalysisId) {
            loadHistoryAnalysis(activeAnalysisId);
        }
    }
);
