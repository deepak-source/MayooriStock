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

PAGE_SIZE = 12

st.set_page_config(page_title="Lead Accounting Plus | Stock Report", layout="wide")

# ---------------- LOGIN STATE ----------------
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False

if "login_info" not in st.session_state:
    st.session_state.login_info = {}

    # 🔥 ALWAYS sync AUTH from session (AFTER init)
if st.session_state.get("login_info"):
    AUTH_PAYLOAD["oid"] = st.session_state.login_info.get("oid", AUTH_PAYLOAD["oid"])
    AUTH_PAYLOAD["sid"] = st.session_state.login_info.get("sid", AUTH_PAYLOAD["sid"])

# Directory for PDF images
os.makedirs("pdf_images", exist_ok=True)




# ---------------- HELPERS ----------------
def has_stock(qty):
    try:
        return float(qty) > 0
    except:
        return False


def api_login(userid, password, location="1"):
    payload = {
        "comid": AUTH_PAYLOAD["comid"],
        "comkey": AUTH_PAYLOAD["comkey"],
        "userid": userid,
        "password": password,
        "location": location,
        "till": ""
    }

    try:
        res = requests.post(f"{BASE_URL}/login", json=payload).json()
        return res
    except:
        return {"status": "failed", "message": "Login failed"}

def download_and_prepare_image(url, goods_id):
    try:
        path = f"pdf_images/{goods_id}.jpg"

        # ✅ if already downloaded → reuse (BIG SPEED BOOST)
        if os.path.exists(path):
            return path

        r = requests.get(url, timeout=8)
        r.raise_for_status()

        img = Image.open(BytesIO(r.content)).convert("RGB")
        img.save(path, format="JPEG", quality=85)

        return path
    except:
        return None

def safe_post_json(url, payload, timeout=15):
    try:
        response = requests.post(url, json=payload, timeout=timeout)

        # 🔴 if server error
        if response.status_code != 200:
            return {}

        # 🔴 safe JSON parse
        try:
            return response.json()
        except Exception:
            return {}

    except Exception:
        return {}

# ---------------- COMMON APIs ----------------
def get_locations():
    payload = {
        **AUTH_PAYLOAD,
        "startrow": "0",
        "page": "1",
        "pagesize": "100",
        "type": "location"
    }
    data = safe_post_json(f"{BASE_URL}/getrows", payload)
    return data.get("items", [])

def get_goods_for_pdf(page, search="", category="", vendor=""):
    payload = {
        **AUTH_PAYLOAD,
        "startrow": str((page - 1) * 200 + 1),
        "page": str(page),
        "pagesize": "200",
        "goods": "",
        "barcode": search,
        "name": search,
        "category": category,
        "account": "",
        "online": "",
        "vendor": vendor
    }

    try:
        res = requests.post(f"{BASE_URL}/getgoods", json=payload, timeout=15)
        return res.json()
    except Exception:
        return {"items": [], "totalrows": 0}


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

@st.cache_data(ttl=3600)
def get_item_images(goods_id):
    payload = {
        **AUTH_PAYLOAD,
        "goods": goods_id
    }

    try:
        response = requests.post(
            f"{BASE_URL}/getimages",
            json=payload,
            timeout=10
        )

        # ✅ check HTTP status
        if response.status_code != 200:
            return []

        # ✅ safe JSON parse
        try:
            data = response.json()
        except Exception:
            return []

        return [img.get("text") for img in data.get("list", []) if img.get("text")]

    except Exception:
        return []


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


def export_full_stock_to_pdf(location_id, search_text, category_id="", vendor_id=""):
    pdf = StockPDF()
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.table_header()

    # ---------- progress UI ----------
    progress_bar = st.progress(0)
    status_text = st.empty()

    total_rows_estimate = None
    processed = 0

    # ---------- layout constants ----------
    IMAGE_COL_W = 35
    ITEM_COL_W = 55
    CODE_COL_W = 30
    UNIT_COL_W = 15
    QTY_COL_W = 20
    AMT_COL_W = 25

    MIN_ROW_HEIGHT = 40
    LINE_HEIGHT = 5

    page = 1

    while True:
        data = get_goods_for_pdf(
            page,
            search_text,
            category_id,
            vendor_id
        )

        items = data.get("items", [])
        if not items:
            break

        # ✅ lock total rows from first response
        if total_rows_estimate is None:
            try:
                total_rows_estimate = int(data.get("totalrows", 0))
            except:
                total_rows_estimate = 1

        for item in items:
            processed += 1

            # ---------- progress update ----------
            total_for_progress = max(total_rows_estimate or 1, 1)
            progress = min(processed / total_for_progress, 1.0)

            progress_bar.progress(progress)
            status_text.text(f"Generating PDF… {processed}/{total_for_progress}")

            # ---------- calculate wrapped height ----------
            pdf.set_font("Arial", size=9)

            item_name = str(item.get("name", ""))

            # better wrap estimation
            text_width = pdf.get_string_width(item_name)
            chars_per_line = max(int(ITEM_COL_W / 2.5), 1)
            nb_lines = max(1, math.ceil(len(item_name) / chars_per_line))

            wrapped_height = nb_lines * LINE_HEIGHT
            row_height = max(MIN_ROW_HEIGHT, wrapped_height)

            # ---------- page break ----------
            if pdf.get_y() + row_height > 270:
                pdf.add_page()
                pdf.table_header()

            x_start = pdf.get_x()
            y_start = pdf.get_y()

            # ---------- IMAGE CELL ----------
            pdf.cell(IMAGE_COL_W, row_height, "", border=1)

            img_url = item.get("image")
            if img_url:
                img_path = download_and_prepare_image(img_url, item["id"])
                if img_path:
                    try:
                        pdf.image(
                            img_path,
                            x=x_start + 2,
                            y=y_start + 2,
                            w=IMAGE_COL_W - 5,
                            h=IMAGE_COL_W - 5,
                        )
                    except Exception:
                        pass

            # ---------- ITEM NAME (wrapped) ----------
            pdf.set_xy(x_start + IMAGE_COL_W, y_start)
            x_after_item = pdf.get_x()

            pdf.multi_cell(ITEM_COL_W, LINE_HEIGHT, item_name, border=1)

            # restore cursor
            pdf.set_xy(x_after_item + ITEM_COL_W, y_start)

            # ---------- remaining columns ----------
            pdf.cell(CODE_COL_W, row_height, str(item.get("code", "-")), border=1)
            pdf.cell(UNIT_COL_W, row_height, str(item.get("unit", "")), border=1, align="C")
            pdf.cell(QTY_COL_W, row_height, str(item.get("stock", "")), border=1, align="R")
            pdf.cell(AMT_COL_W, row_height, str(item.get("price", "")), border=1, align="R")

            pdf.ln(row_height)

        # ---------- correct pagination stop ----------
        try:
            total_pages = int(data.get("pages", 1))
        except:
            total_pages = 1

        if page >= total_pages:
            break

        page += 1

    progress_bar.progress(1.0)
    status_text.text("✅ PDF ready")

    return pdf.output(dest="S").encode("latin1")

# ---------------- LOGIN UI ----------------
if not st.session_state.is_logged_in:
    st.title("🔐 Login")

    c1, c2, c3 = st.columns([2,2,2])

    with c1:
        login_user = st.text_input("User ID")

    with c2:
        login_pass = st.text_input("Password", type="password")

    with c3:
        login_loc = st.text_input("Location", value="1")

    if st.button("🚀 Login"):
        result = api_login(login_user, login_pass, login_loc)

        if result.get("status") == "success":
            # 🔴 auto logout if session dies
            def ensure_session_alive(data):
                if not data:
                    st.session_state.is_logged_in = False
                    st.error("Session expired. Please login again.")
                    st.stop()
                return data
            st.session_state.is_logged_in = True
            st.session_state.login_info = result

            # 🔥 CRITICAL — update AUTH dynamically
            AUTH_PAYLOAD["oid"] = result.get("oid")
            AUTH_PAYLOAD["sid"] = result.get("sid")

            # 🔥 CRITICAL — clear stale cache
            st.cache_data.clear()

            st.rerun()
        else:
            st.error(result.get("message", "Login failed"))

    st.stop()

# ---------------- ROLE CHECK ----------------
vendor_login_id = st.session_state.login_info.get("vendor", "0")

if vendor_login_id and vendor_login_id != "0":
    tab_stock = st.tabs(["📦 Stock Report"])[0]
    tab_po = None
else:
    tab_stock, tab_po = st.tabs(["📦 Stock Report", "🧾 Purchase Order"])

# =====================================================
# 📦 STOCK TAB (UPDATED TO GETGOODS)
# =====================================================
with tab_stock:
    st.title("📦 Stock Report")

    @st.cache_data(ttl=600)
    def get_vendors():
        payload = {
            **AUTH_PAYLOAD,
            "startrow": "0",
            "page": "1",
            "pagesize": "1000",
            "type": "account"
        }
        data = safe_post_json(f"{BASE_URL}/getrows", payload)
        return data.get("items", [])

    @st.cache_data(ttl=600)
    def get_categories(parent_id=""):
        payload = {
            **AUTH_PAYLOAD,
            "startrow": "0",
            "page": "1",
            "pagesize": "100",
            "type": "category",
            "document": "7",
            "parent": parent_id
        }
        data = safe_post_json(f"{BASE_URL}/getrows", payload)
        return data.get("items", [])

    def get_goods(page, location_id="", search="", category="", vendor=""):
        payload = {
            **AUTH_PAYLOAD,
            "startrow": str((page - 1) * PAGE_SIZE + 1),
            "page": str(page),
            "pagesize": str(PAGE_SIZE),
            "goods": "",
            "barcode": search,
            "name": search,
            "category": category,
            "account": "",
            "online": "",
            "vendor": vendor
        }
        return safe_post_json(f"{BASE_URL}/getgoods", payload)

    # -------- FILTER ROW --------
    locations = get_locations()
    vendors = get_vendors()
    parent_categories = get_categories("")

    f1, f2, f3, f4 = st.columns([2, 2, 2, 3])

    location_map = {"All Locations": ""}
    for loc in locations:
        location_map[loc["name"]] = loc["id"]
    selected_location = f1.selectbox("Location", location_map.keys())
    location_id = location_map[selected_location]

    vendor_map = {"All Vendors": ""}
    for v in vendors:
        vendor_map[v["name"]] = v["id"]
# -------- Vendor handling (role based) --------
    vendor_login_id = st.session_state.login_info.get("vendor", "0")

    if vendor_login_id and vendor_login_id != "0":
        # vendor user — force select
        forced_vendor_name = next(
            (name for name, vid in vendor_map.items() if vid == vendor_login_id),
            "All Vendors"
        )
        selected_vendor = f2.selectbox(
            "Vendor",
            vendor_map.keys(),
            index=list(vendor_map.keys()).index(forced_vendor_name),
            disabled=True
        )
        vendor_id = vendor_login_id
    else:
        selected_vendor = f2.selectbox("Vendor", vendor_map.keys())
        vendor_id = vendor_map[selected_vendor]

    # ---------- CATEGORY HIERARCHY PICKER ----------

    if "category_path" not in st.session_state:
        st.session_state.category_path = []


    # Show selected tags
    if st.session_state.category_path:
        tag_cols = st.columns(len(st.session_state.category_path))
        for i, cat in enumerate(st.session_state.category_path):
            with tag_cols[i]:
                if st.button(f"❌ {cat['name']}", key=f"cat_tag_{i}"):
                    st.session_state.category_path = st.session_state.category_path[:i]
                    st.rerun()

    # Determine current parent
    current_parent = (
        st.session_state.category_path[-1]["id"]
        if st.session_state.category_path
        else ""
    )

    # Load next level
    next_categories = get_categories(current_parent)

    # ---------- CATEGORY DROPDOWN ----------
    cat_options = ["Select Category"] + [c["name"] for c in next_categories]

    selected_cat = f3.selectbox(
        "Category",
        cat_options,
        key="category_selector"
    )

    if selected_cat != "Select Category":
        selected_obj = next(
            c for c in next_categories if c["name"] == selected_cat
        )

        st.session_state.category_path.append({
            "id": selected_obj["id"],
            "name": selected_obj["name"]
        })

        # ✅ SAFE reset using deletion (Streamlit-approved)
        if "category_selector" in st.session_state:
            del st.session_state["category_selector"]

        st.rerun()

    # Final category id for API
    category_id = (
        st.session_state.category_path[-1]["id"]
        if st.session_state.category_path
        else ""
    )

    # parent_map = {"All Categories": ""}
    # for c in parent_categories:
    #     parent_map[c["name"]] = c["id"]
    # selected_parent = f3.selectbox("Parent Category", parent_map.keys())
    # parent_id = parent_map[selected_parent]

    # child_categories = get_categories(parent_id) if parent_id else []
    # child_map = {"All Subcategories": ""}
    # for c in child_categories:
    #     child_map[c["name"]] = c["id"]
    # selected_child = f4.selectbox("Sub Category", child_map.keys())
    # category_id = child_map[selected_child] or parent_id



    search_text = f4.text_input("🔍 Search", placeholder="Name or barcode...")

    if "page" not in st.session_state:
        st.session_state.page = 1

    data = get_goods(
        st.session_state.page,
        location_id,
        search_text,
        category_id,
        vendor_id
    )

    items = data.get("items", [])
    total_rows = int(data.get("totalrows", 0))
    total_pages = math.ceil(total_rows / PAGE_SIZE)

    st.markdown("### Stock Items")

    if not items:
        st.info("No items found.")
    else:
        cols_per_row = 4
        rows = math.ceil(len(items) / cols_per_row)

        idx = 0
        for _ in range(rows):
            cols = st.columns(cols_per_row)
            for col in cols:
                if idx >= len(items):
                    break
                item = items[idx]
                with col:
                    st.markdown(
                        f"""
                        <div style="
                            height:160px;
                            display:flex;
                            align-items:center;
                            justify-content:center;
                            border:1px solid #eee;
                            border-radius:8px;
                            background:#fafafa;
                            margin-bottom:6px;
                        ">
                            <img src="{item.get('image','')}"
                                style="max-height:140px;
                                        max-width:100%;
                                        object-fit:contain;" />
                        </div>
                        """,
                        unsafe_allow_html=True
)
                    st.markdown(f"**{item['name']}**")
                    st.caption(f"Code: {item.get('code','-')}")
                    st.caption(f"Unit: {item.get('unit','-')}")
                    st.caption(f"Stock: {item.get('stock','0')}")
                    st.caption(f"Price: ₹{item.get('price','0')}")
                idx += 1

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

    st.markdown("---")

    if st.button("📄 Export Full Stock to PDF"):

        vendor_login_id = st.session_state.login_info.get("vendor", "0")

        # 🔥 if vendor user → force vendor filter
        export_vendor_id = (
            vendor_login_id if vendor_login_id and vendor_login_id != "0"
            else vendor_id
        )

        pdf_bytes = export_full_stock_to_pdf(
            location_id,
            search_text,
            category_id,
            export_vendor_id
        )
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="stock_report.pdf",
            mime="application/pdf"
        )

if tab_po is not None:
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


        
