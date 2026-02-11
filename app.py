import streamlit as st
import requests
from fpdf import FPDF
from PIL import Image
from io import BytesIO
import math
import os

# ---------------- CONFIG ----------------
BASE_URL = "https://leadapi-crchenf4csgagcef.centralindia-01.azurewebsites.net/api"

AUTH_PAYLOAD = {
    "comid": "19621273",
    "comkey": "82246338",
    "oid": "4",
    "sid": "274"
}

PAGE_SIZE = 10

st.set_page_config(page_title="Lead Accounting Plus | Stock Report", layout="wide")

# Directory for PDF images
os.makedirs("pdf_images", exist_ok=True)


tab_stock, tab_po = st.tabs(["📦 Stock Report", "🧾 Purchase Order"])


# ---------------- HELPERS ----------------
def has_stock(qty):
    try:
        return float(qty) > 0
    except:
        return False


def download_and_prepare_image(url, goods_id):
    """
    Downloads image from URL, converts to RGB JPEG and saves locally.
    This is REQUIRED for FPDF to render images.
    """
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()

        img = Image.open(BytesIO(r.content))
        img = img.convert("RGB")  # CRITICAL

        path = f"pdf_images/{goods_id}.jpg"
        img.save(path, format="JPEG", quality=85)

        return path
    except:
        return None


# ---------------- API HELPERS ----------------
def get_locations():
    payload = {
        **AUTH_PAYLOAD,
        "startrow": "0",
        "page": "1",
        "pagesize": "100",
        "type": "location"
    }
    return requests.post(f"{BASE_URL}/getrows", json=payload).json().get("items", [])


def get_inventory(page, location_id="", search=""):
    payload = {
        **AUTH_PAYLOAD,
        "startrow": str((page - 1) * PAGE_SIZE + 1),
        "page": str(page),
        "pagesize": str(PAGE_SIZE),
        "date": "2026-02-09",
        "category": "",
        "location": location_id,
        "name": search
    }
    return requests.post(f"{BASE_URL}/inventory", json=payload).json()


def get_item_images(goods_id):
    payload = {
        **AUTH_PAYLOAD,
        "goods": goods_id
    }
    r = requests.post(f"{BASE_URL}/getimages", json=payload).json()
    return [img["text"] for img in r.get("list", [])]


# ---------------- PDF EXPORT ----------------
class StockPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "Stock Report - Lead Accounting Plus", ln=True, align="C")
        self.ln(4)

    def table_header(self):
        self.set_font("Arial", "B", 9)
        self.cell(35, 8, "Image", border=1, align="C")
        self.cell(55, 8, "Item", border=1)
        self.cell(30, 8, "Code", border=1)
        self.cell(15, 8, "Unit", border=1, align="C")
        self.cell(20, 8, "Qty", border=1, align="R")
        self.cell(25, 8, "Amount", border=1, align="R")
        self.ln()


def export_full_stock_to_pdf(location_id, search_text):
    pdf = StockPDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.table_header()

    row_height = 40
    rows_per_page = 5
    row_count = 0

    page = 1
    while True:
        data = get_inventory(page, location_id, search_text)
        items = data.get("items", [])

        if not items:
            break

        for item in items:
            if not has_stock(item.get("quantity")):
                continue

            if row_count >= rows_per_page:
                pdf.add_page()
                pdf.table_header()
                row_count = 0

            x = pdf.get_x()
            y = pdf.get_y()

            # Image cell
            pdf.cell(35, row_height, "", border=1)

            images = get_item_images(item["id"])
            if images:
                img_path = download_and_prepare_image(images[0], item["id"])
                if img_path:
                    pdf.image(
                        img_path,
                        x=x + 2,
                        y=y + 2,
                        w=30,
                        h=30
                    )

            pdf.set_xy(x + 35, y)

            pdf.set_font("Arial", size=9)
            pdf.cell(55, row_height, item["name"], border=1)
            pdf.cell(30, row_height, item["code"] or "-", border=1)
            pdf.cell(15, row_height, item["unit"], border=1, align="C")
            pdf.cell(20, row_height, item["quantity"], border=1, align="R")
            pdf.cell(25, row_height, item["amount"], border=1, align="R")
            pdf.ln(row_height)

            row_count += 1

        total_pages = math.ceil(int(data["totalrows"]) / PAGE_SIZE)
        if page >= total_pages:
            break
        page += 1

    return pdf.output(dest="S").encode("latin1")


# ---------------- UI ----------------

with tab_stock:
    st.title("📦 Stock Report")

    locations = get_locations()
    location_map = {"All Locations": ""}
    for loc in locations:
        location_map[loc["name"]] = loc["id"]

    selected_location = st.selectbox("Select Location", location_map.keys())
    location_id = location_map[selected_location]

    search_text = st.text_input(
        "🔍 Search item by name or code",
        placeholder="Type item name or barcode..."
    )

    if "page" not in st.session_state:
        st.session_state.page = 1

    data = get_inventory(st.session_state.page, location_id, search_text)

    items = [
        item for item in data.get("items", [])
        # if has_stock(item.get("quantity"))
    ]

    total_rows = int(data.get("totalrows", 0))
    total_pages = math.ceil(total_rows / PAGE_SIZE)

    st.markdown("### Stock Items")

    if not items:
        st.info("No items found with stock.")
    else:
        for item in items:
            col1, col2 = st.columns([1, 3])

            with col1:
                images = get_item_images(item["id"])
                if images:
                    st.markdown(
                        f"""
                        <div style="height:120px; overflow-y:auto">
                            {''.join([f'<img src="{img}" width="100"><br>' for img in images])}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    st.write("No Image")

            with col2:
                st.write(f"**{item['name']}**")
                st.write(f"Code: {item['code']}")
                st.write(f"Unit: {item['unit']} | Qty: {item['quantity']} | Amount: ₹{item['amount']}")

            st.divider()

    # Pagination
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("⬅ Previous") and st.session_state.page > 1:
            st.session_state.page -= 1
            st.rerun()

    with col2:
        st.write(f"Page {st.session_state.page} of {total_pages}")

    with col3:
        if st.button("Next ➡") and st.session_state.page < total_pages:
            st.session_state.page += 1
            st.rerun()

    # Export
    st.markdown("---")

    if st.button("📄 Export Full Stock to PDF"):
        pdf_bytes = export_full_stock_to_pdf(location_id, search_text)
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="stock_report.pdf",
            mime="application/pdf"
        )

with tab_po:
    st.title("🧾 Multi-Location Purchase Order")

    # ---------------- API HELPERS (PO ONLY) ----------------
    @st.cache_data(ttl=600)
    def get_accounts():
        payload = {
            **AUTH_PAYLOAD,
            "startrow": "0",
            "page": "1",
            "pagesize": "1000",
            "type": "account"
        }
        return requests.post(
            f"{BASE_URL}/getrows", json=payload
        ).json().get("items", [])

    @st.cache_data(ttl=600)
    def get_all_items_for_po():
        payload = {
            **AUTH_PAYLOAD,
            "startrow": "1",
            "page": "1",
            "pagesize": "1000",
            "date": "2026-02-09",
            "location": "",
            "name": ""
        }
        return requests.post(
            f"{BASE_URL}/inventory", json=payload
        ).json().get("items", [])

    # ---------------- DATA ----------------
    accounts = get_accounts()
    locations = get_locations()
    items = get_all_items_for_po()

    account_map = {a["name"]: a["id"] for a in accounts}
    location_map = {l["name"]: l["id"] for l in locations}
    item_map = {i["name"]: i["id"] for i in items}

    # ---------------- STATE ----------------
    if "po_lines" not in st.session_state:
        st.session_state.po_lines = [
            {"item": "", "location": "", "qty": 0.0, "rate": 0.0}
            for _ in range(100)
        ]

    # ---------------- ADD / CLEAR ----------------
    col_add, col_clear = st.columns([1, 1])

    with col_add:
        if st.button("➕ Add Item"):
            st.session_state.po_lines.append(
                {"item": "", "location": "", "qty": 0.0, "rate": 0.0}
            )

    with col_clear:
        if st.button("🧹 Clear All"):
            st.session_state.po_lines = [
                {"item": "", "location": "", "qty": 0.0, "rate": 0.0}
                for _ in range(100)
            ]

    # ---------------- FORM ----------------
    with st.form("po_form"):
        st.subheader("PO Items")

        vendor_name = st.selectbox("Vendor", account_map.keys())
        vendor_id = account_map[vendor_name]

        st.markdown("---")

        # ---------- STICKY HEADER ----------
        st.markdown(
            """
            <style>
            .po-table {
                max-height: 320px;
                overflow-y: auto;
                border: 1px solid #ddd;
            }
            .po-header {
                position: sticky;
                top: 0;
                background: white;
                z-index: 10;
                border-bottom: 1px solid #ccc;
                padding-top: 4px;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        # Header row
        header = st.container()
        with header:
            c0, c1, c2, c3, c4 = st.columns([0.6, 3, 3, 1.3, 1.3])
            c0.markdown("**#**")
            c1.markdown("**Item**")
            c2.markdown("**Location**")
            c3.markdown("**Qty**")
            c4.markdown("**Rate**")

        # Scrollable rows
        st.markdown("<div class='po-table'>", unsafe_allow_html=True)

        for idx, line in enumerate(st.session_state.po_lines):
            c0, c1, c2, c3, c4 = st.columns([0.6, 3, 3, 1.3, 1.3])

            c0.markdown(str(idx + 1))

            line["item"] = c1.selectbox(
                "",
                [""] + list(item_map.keys()),
                index=([""] + list(item_map.keys())).index(line["item"])
                if line["item"] in item_map else 0,
                key=f"po_item_{idx}"
            )

            line["location"] = c2.selectbox(
                "",
                [""] + list(location_map.keys()),
                index=([""] + list(location_map.keys())).index(line["location"])
                if line["location"] in location_map else 0,
                key=f"po_loc_{idx}"
            )

            line["qty"] = c3.number_input(
                "",
                min_value=0.0,
                value=float(line["qty"]),
                key=f"po_qty_{idx}"
            )

            line["rate"] = c4.number_input(
                "",
                min_value=0.0,
                value=float(line["rate"]),
                key=f"po_rate_{idx}"
            )

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")
        submitted = st.form_submit_button("🚀 Create Purchase Orders")

    # ---------------- SUBMIT HANDLER ----------------
    if submitted:
        grouped_by_location = {}

        for line in st.session_state.po_lines:
            if (
                line["item"]
                and line["location"]
                and line["qty"] > 0
                and line["rate"] > 0
            ):
                loc_id = location_map[line["location"]]
                grouped_by_location.setdefault(loc_id, []).append(line)

        for loc_id, lines in grouped_by_location.items():
            payload = {
                **AUTH_PAYLOAD,
                "id": "",
                "document": "15",
                "subdocument": "15",
                "location": loc_id,
                "date": "2026-02-09",
                "account": vendor_id,
                "number": "",
                "lines": [
                    {
                        "goods": item_map[l["item"]],
                        "barcode": "",
                        "batch": "",
                        "batchnumber": "",
                        "quantity": str(l["qty"]),
                        "free": "N",
                        "rate": str(l["rate"]),
                        "discount": "0",
                        "narration": l["item"]
                    }
                    for l in lines
                ],
                "others": []
            }

            requests.post(
                f"{BASE_URL}/possave",
                json=payload
            )

        st.success("✅ Purchase Orders created successfully (location-wise)")


        
