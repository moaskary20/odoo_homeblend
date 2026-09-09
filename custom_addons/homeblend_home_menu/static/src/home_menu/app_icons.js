/** Classic Enterprise home-menu glyphs and colors (Font Awesome 4). */

const BY_MODULE = {
    mail: { icon: "fa fa-comments", bg: "#00A09D" },
    calendar: { icon: "fa fa-calendar", bg: "#F06050" },
    note: { icon: "fa fa-sticky-note", bg: "#F7CD1F" },
    project_todo: { icon: "fa fa-check-square-o", bg: "#F7CD1F" },
    contacts: { icon: "fa fa-address-book-o", bg: "#1f7eaa" },
    crm: { icon: "fa fa-heart", bg: "#00A09D" },
    sale: { icon: "fa fa-usd", bg: "#00A09D" },
    sale_management: { icon: "fa fa-usd", bg: "#00A09D" },
    point_of_sale: { icon: "fa fa-shopping-cart", bg: "#7C7BAD" },
    account: { icon: "fa fa-money", bg: "#475577" },
    project: { icon: "fa fa-puzzle-piece", bg: "#F06050" },
    hr_timesheet: { icon: "fa fa-clock-o", bg: "#C4A000" },
    website: { icon: "fa fa-globe", bg: "#1f7eaa" },
    website_slides: { icon: "fa fa-graduation-cap", bg: "#5B899E" },
    mass_mailing: { icon: "fa fa-envelope", bg: "#2C8397" },
    event: { icon: "fa fa-ticket", bg: "#7C7BAD" },
    survey: { icon: "fa fa-check-square-o", bg: "#F06050" },
    purchase: { icon: "fa fa-credit-card", bg: "#1f7eaa" },
    stock: { icon: "fa fa-cubes", bg: "#7C4949" },
    mrp: { icon: "fa fa-cogs", bg: "#7C7BAD" },
    hr: { icon: "fa fa-users", bg: "#00A09D" },
    hr_recruitment: { icon: "fa fa-user-plus", bg: "#F06050" },
    hr_holidays: { icon: "fa fa-plane", bg: "#00A09D" },
    hr_attendance: { icon: "fa fa-check", bg: "#7C7BAD" },
    hr_expense: { icon: "fa fa-money", bg: "#C4A000" },
    fleet: { icon: "fa fa-car", bg: "#1f7eaa" },
    maintenance: { icon: "fa fa-wrench", bg: "#7C7BAD" },
    lunch: { icon: "fa fa-cutlery", bg: "#F06050" },
    im_livechat: { icon: "fa fa-comments-o", bg: "#00A09D" },
    repair: { icon: "fa fa-wrench", bg: "#7C4949" },
    website_sale: { icon: "fa fa-shopping-cart", bg: "#00A09D" },
    website_event: { icon: "fa fa-ticket", bg: "#7C7BAD" },
    website_hr_recruitment: { icon: "fa fa-user-plus", bg: "#F06050" },
    spreadsheet_dashboard: { icon: "fa fa-tachometer", bg: "#875A7B" },
    base: { icon: "fa fa-cogs", bg: "#875A7B" },
    utm: { icon: "fa fa-link", bg: "#1f7eaa" },
    marketing_card: { icon: "fa fa-id-card-o", bg: "#00A09D" },
    mass_mailing_sms: { icon: "fa fa-mobile", bg: "#2C8397" },
    pos_restaurant: { icon: "fa fa-cutlery", bg: "#7C7BAD" },
    data_recycle: { icon: "fa fa-recycle", bg: "#475577" },
};

const PALETTE = [
    "#00A09D",
    "#F06050",
    "#475577",
    "#7C7BAD",
    "#1f7eaa",
    "#C4A000",
    "#7C4949",
    "#875A7B",
];

function colorFromString(value) {
    let hash = 0;
    for (const char of value || "") {
        hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
    }
    return PALETTE[hash % PALETTE.length];
}

export function getAppIcon(app) {
    const xmlid = app.xmlid || "";
    const module = xmlid.split(".")[0];
    if (BY_MODULE[module]) {
        return BY_MODULE[module];
    }
    if (xmlid.includes("settings") || xmlid.includes("administration")) {
        return { icon: "fa fa-cogs", bg: "#875A7B" };
    }
    if (xmlid.includes("module") || xmlid.includes("apps")) {
        return { icon: "fa fa-th-large", bg: "#00A09D" };
    }
    return { icon: "fa fa-th-large", bg: colorFromString(xmlid || app.name) };
}
