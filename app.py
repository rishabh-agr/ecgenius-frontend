import streamlit as st
import requests
import json
from datetime import date
import matplotlib.pyplot as plt
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import matplotlib.pyplot as plt
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import json




# =========================
# CONFIG
# =========================


REGISTER_ENDPOINT = f"http://44.192.254.95/register"
GET_REPORT_ENDPOINT = f"http://44.192.254.95/get_report"


def build_prediction_id(pred_date: date, unique_code: str) -> str:
    """
    Combine date + unique code to form prediction_id.
    Example format: 2025-11-25-ABC12345
    """
    date_str = pred_date.strftime("%Y-%m-%d")
    cleaned_code = unique_code.strip().replace(" ", "")
    return f"{date_str}-{cleaned_code}"


# =========================
# PAGE 1: REGISTER PATIENT
# =========================

def page_register():
    st.title("🫀 ECGenius - Patient Registration")
    st.write("Register a patient for an existing prediction ID.")

    with st.form("register_form"):
        st.subheader("Prediction Details")
        pred_date = st.date_input("Prediction Date", value=date.today())
        unique_code = st.text_input(
            "Prediction Unique Code",
            placeholder="e.g. 12345678",
            max_chars=20,
        )

        st.subheader("Patient Details")
        name = st.text_input("Full Name", placeholder="Rishabh Kumar")
        age = st.number_input("Age", min_value=0, max_value=120, step=1)
        gender = st.selectbox("Gender", ["M", "F", "O"])
        phone_no = st.text_input("Phone Number", placeholder="9876543210", max_chars=15)
        previous_medication = st.text_area(
            "Previous Medication",
            placeholder="e.g. Atorvastatin 10mg, Aspirin 75mg",
            height=100,
        )

        submitted = st.form_submit_button("Register Patient")

    if submitted:
        errors = []

        if not unique_code.strip():
            errors.append("Prediction unique code is required.")

        if not name.strip():
            errors.append("Name is required.")

        if age <= 0:
            errors.append("Age must be greater than 0.")

        if not phone_no.strip():
            errors.append("Phone number is required.")

        if not previous_medication.strip():
            errors.append("Previous medication is required.")

        if errors:
            for e in errors:
                st.error(e)
            st.stop()

        prediction_id = build_prediction_id(pred_date, unique_code)
        st.info(f"Using prediction_id: **{prediction_id}**")

        payload = {
            "prediction_id": prediction_id,
            "name": name.strip(),
            "age": int(age),
            "gender": gender,
            "phone_no": phone_no.strip(),
            "previous_medication": previous_medication.strip(),
        }

        try:
            with st.spinner("Registering patient..."):
                resp = requests.post(REGISTER_ENDPOINT, json=payload, timeout=10)

            try:
                data = resp.json()
            except Exception:
                data = {"error": "Non-JSON response from server", "raw_text": resp.text}

            if resp.status_code == 200:
                st.success("✅ Patient registered successfully!")
                st.write(f"Prediction ID: **{prediction_id}**")
                # You can show minimal info instead of full JSON
                record = data.get("record") or {}
                with st.expander("View saved record"):
                    st.write(record)

            elif resp.status_code == 404:
                st.error("❌ Prediction not found. Please check prediction date & code.")
                st.write(data.get("error", ""))

            elif resp.status_code == 409:
                st.warning("⚠️ Patient already registered for this prediction_id.")
                st.write(data.get("error", ""))

            elif resp.status_code == 400:
                st.error("❌ Bad request. Some fields may be missing or invalid.")
                st.write(data.get("error", ""))

            else:
                st.error(f"❌ Unexpected error: HTTP {resp.status_code}")
                st.write(data)

        except requests.exceptions.RequestException as e:
            st.error(f"Failed to connect to backend API: {e}")

#========= generate PDF

def generate_pdf_report(report: dict) -> bytes:
    """
    Create a PDF report (with ECG waveform image if available)
    and return it as raw bytes.
    """

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x_margin = 40
    y = height - 50

    def line(text: str = "", font="Helvetica", size=11, gap=16, bold=False):
        nonlocal y
        if y < 80:  # new page if near bottom
            c.showPage()
            y = height - 50
        if bold:
            c.setFont("Helvetica-Bold", size)
        else:
            c.setFont(font, size)
        c.drawString(x_margin, y, text)
        y -= gap

    # ===== Header =====
    line("ECGenius - Patient Report", size=18, bold=True, gap=24)
    line(f"Prediction ID: {report.get('prediction_id', 'N/A')}", bold=True, gap=18)
    line(f"Timestamp: {report.get('timestamp', 'N/A')}", gap=18)

    # ===== Patient Info =====
    line()
    line("Patient Details", size=14, bold=True, gap=20)
    line(f"Name      : {report.get('name', 'N/A')}")
    line(f"Age       : {report.get('age', 'N/A')}")
    line(f"Gender    : {report.get('gender', 'N/A')}")
    line(f"Phone No. : {report.get('phone_no', 'N/A')}")

    # ===== Medication =====
    line()
    line("Previous Medication", size=14, bold=True, gap=20)
    prev_med = report.get("previous_medication", "Not provided") or "Not provided"

    max_chars = 90
    med_text = str(prev_med)
    for i in range(0, len(med_text), max_chars):
        line(med_text[i:i + max_chars])

    # ===== Prediction Results =====
    line()
    line("ECG Prediction Results", size=14, bold=True, gap=20)

    results = report.get("results", {})
    conditions = [
        ("is_mci", "Myocardial Ischemia (MCI)"),
        ("is_afib", "Atrial Fibrillation (AFib)"),
        ("is_bbb", "Bundle Branch Block (BBB)"),
        ("is_vfi", "Ventricular Fibrillation (VFib)"),
    ]

    def flag_to_text(v):
        if v is True:
            return "Detected"
        if v is False:
            return "Not Detected"
        return "Unknown"

    for key, label in conditions:
        val = results.get(key)
        line(f"{label:35s}: {flag_to_text(val)}")

    # ===== ECG Info & Waveform =====
    line()
    line("ECG Signal", size=14, bold=True, gap=20)

    samples = report.get("samples")
    y_samples = normalize_samples(samples)
    if y_samples:
        line(f"Number of samples recorded: {len(y_samples)}", gap=18)
    else:
        line("ECG samples not available in this report.", gap=18)

    # Try to draw ECG image
    img_buf = create_ecg_png_bytes(samples)
    if img_buf is not None:
        img = ImageReader(img_buf)
        img_width, img_height = img.getSize()

        # Scale image to fit within margins
        target_width = width - 2 * x_margin
        scale = target_width / img_width
        target_height = img_height * scale

        # New page if not enough vertical space
        if y - target_height < 60:
            c.showPage()
            y = height - 80

        c.drawImage(
            img,
            x_margin,
            y - target_height,
            width=target_width,
            height=target_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        y -= target_height + 20
    else:
        # No image: nothing more to do here
        pass

    # ===== Footer =====
    line()
    line("Generated by ECGenius", size=9, gap=12)
    line("This report is for clinical review by a qualified physician.", size=8, gap=10)

    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def normalize_samples(samples_raw):
    """
    Try to turn whatever 'samples' is (list, JSON string, CSV string, numpy, etc.)
    into a Python list of floats. Returns None if it fails.
    """
    if samples_raw is None:
        return None

    try:
        # Already list/tuple
        if isinstance(samples_raw, (list, tuple)):
            return [float(v) for v in samples_raw]

        # Numpy-like
        if hasattr(samples_raw, "tolist"):
            return [float(v) for v in samples_raw.tolist()]

        # String formats
        if isinstance(samples_raw, str):
            s = samples_raw.strip()

            # JSON list string: "[0.1, 0.2, ...]"
            if s.startswith("[") and s.endswith("]"):
                parsed = json.loads(s)
                if isinstance(parsed, (list, tuple)):
                    return [float(v) for v in parsed]

            # Comma / semicolon separated: "0.1,0.2,0.3"
            parts = [p for p in s.replace(";", ",").split(",") if p.strip()]
            return [float(p) for p in parts]

    except Exception:
        return None

    return None


def create_ecg_png_bytes(samples_raw) -> BytesIO | None:
    """
    Create a PNG image of the ECG waveform from raw samples.
    Returns a BytesIO object or None if samples are invalid.
    """
    y = normalize_samples(samples_raw)
    if not y or len(y) == 0:
        return None

    x = list(range(len(y)))

    fig, ax = plt.subplots(figsize=(6, 2.5))  # size tuned for PDF
    ax.plot(x, y, linewidth=1)
    ax.set_xlabel("Sample Index")
    ax.set_ylabel("Amplitude")
    ax.set_title("ECG Waveform")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7)

    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="PNG", dpi=200)
    plt.close(fig)
    buf.seek(0)
    return buf


# =========================
# PAGE 2: GET REPORT
# =========================

def page_get_report():
    st.title("📄 ECGenius - Get Report")
    st.write("Enter your prediction details to view the ECGenius report.")

    with st.form("get_report_form"):
        st.subheader("Prediction Details")
        pred_date = st.date_input("Prediction Date", value=date.today())
        unique_code = st.text_input(
            "8-digit Prediction Code",
            placeholder="e.g. 12345678",
            max_chars=8,
        )

        submitted = st.form_submit_button("Fetch Report")

    if submitted:
        errors = []

        code = unique_code.strip()
        if not code:
            errors.append("Prediction code is required.")
        elif len(code) != 8:
            errors.append("Prediction code must be exactly 8 digits (0-9).")

        if errors:
            for e in errors:
                st.error(e)
            st.stop()

        prediction_id = build_prediction_id(pred_date, code)
        st.info(f"Using prediction_id: **{prediction_id}**")

        payload = {"prediction_id": prediction_id}

        try:
            with st.spinner("Fetching report..."):
                resp = requests.post(GET_REPORT_ENDPOINT, json=payload, timeout=10)

            try:
                data = resp.json()
            except Exception:
                st.error("Server returned a non-JSON response.")
                st.write(resp.text)
                return

            if resp.status_code == 200:
                report = data.get("report", {})
                show_fancy_report(report)

                # --- PDF download section ---
                pdf_bytes = generate_pdf_report(report)
                st.download_button(
                    label="📥 Download PDF Report",
                    data=pdf_bytes,
                    file_name=f"ecgenius_report_{report.get('prediction_id', 'unknown')}.pdf",
                    mime="application/pdf",
                )

            elif resp.status_code == 404:
                st.error("❌ Prediction not found. Please check date & 8-digit code.")
                st.write(data.get("error", ""))

            elif resp.status_code == 403:
                st.warning("🚫 Patient not registered for this prediction_id.")
                st.write(data.get("error", ""))

            elif resp.status_code == 400:
                st.error("❌ prediction_id is required (server-side validation failed).")
                st.write(data.get("error", ""))

            else:
                st.error(f"❌ Unexpected error: HTTP {resp.status_code}")
                st.write(data)

        except requests.exceptions.RequestException as e:
            st.error(f"Failed to connect to backend API: {e}")


def show_fancy_report(report: dict):
    """Render the report in a clean, nice UI (no raw JSON)."""

    st.success("✅ Report fetched successfully!")

    # --------- Top-level info (NO raw samples here) ---------
    st.subheader("🧾 Report Summary")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Prediction ID:** {report.get('prediction_id', 'N/A')}")
        st.write(f"**Timestamp:** {report.get('timestamp', 'N/A')}")
    with col2:
        st.write(f"**Name:** {report.get('name', 'N/A')}")
        st.write(f"**Age:** {report.get('age', 'N/A')}")
        st.write(f"**Gender:** {report.get('gender', 'N/A')}")
        st.write(f"**Phone:** {report.get('phone_no', 'N/A')}")

    st.markdown("---")

    # --------- Previous medication ---------
    st.subheader("💊 Previous Medication")
    prev_med = report.get("previous_medication", "Not provided")
    st.write(prev_med if prev_med else "Not provided")

    st.markdown("---")

    # --------- ECG waveform plot from samples ---------

    st.subheader("📉 ECG Signal")

    samples = report.get("samples")

    y = None

    try:
        if isinstance(samples, str):
            # Try JSON parsing first: "[0.1,0.2,0.3]"
            if samples.strip().startswith("["):
                y = json.loads(samples)
            else:
                # Try comma separated "0.1,0.2,0.3"
                y = [float(x) for x in samples.replace(";", ",").split(",") if x.strip()]
        elif isinstance(samples, (list, tuple)):
            y = [float(v) for v in samples]
        else:
            # attempts for numpy arrays
            if hasattr(samples, "tolist"):
                y = samples.tolist()
    except Exception:
        y = None

    if y and len(y) > 0:
        x = list(range(len(y)))
        st.caption(f"Plotting {len(y)} ECG samples.")

        fig, ax = plt.subplots()
        ax.plot(x, y)
        ax.set_xlabel("Sample Index")
        ax.set_ylabel("Amplitude")
        ax.set_title("ECG Waveform")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7)
        st.pyplot(fig)
    else:
        st.info("ECG samples are not available in this report.")


    # --------- Prediction results ---------
    st.subheader("🩺 ECG Prediction Results")

    results = report.get("results", {})
    conditions = [
        ("is_mci", "Myocardial Ischemia (MCI)"),
        ("is_afib", "Atrial Fibrillation (AFib)"),
        ("is_bbb", "Bundle Branch Block (BBB)"),
        ("is_vfi", "Ventricular Fibrillation (VFib)"),
    ]

    cols = st.columns(4)
    for idx, (key, label) in enumerate(conditions):
        val = results.get(key)
        if val is True:
            text = "Detected"
            emoji = "⚠️"
        elif val is False:
            text = "Not Detected"
            emoji = "✅"
        else:
            text = "Unknown"
            emoji = "❔"

        with cols[idx]:
            st.markdown(f"**{label}**")
            st.markdown(f"{emoji} {text}")



# =========================
# MAIN APP
# =========================

def main():
    st.set_page_config(page_title="ECGenius Portal", page_icon="🫀", layout="centered")

    st.sidebar.title("ECGenius")
    page = st.sidebar.radio(
        "Navigation",
        ("Register Patient", "Get Report"),
    )

    if page == "Register Patient":
        page_register()
    else:
        page_get_report()


if __name__ == "__main__":
    main()
