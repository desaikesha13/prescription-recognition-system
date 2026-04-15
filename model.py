from db import db


class Medicine(db.Model):
    __tablename__ = 'medicines'

    id       = db.Column(db.Integer, primary_key=True)
    brand    = db.Column(db.String(150), nullable=False)
    generic  = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<Medicine {self.brand}>'


class Feedback(db.Model):
    __tablename__ = 'feedback'

    id             = db.Column(db.Integer, primary_key=True)
    image_hash     = db.Column(db.Text)
    original_text  = db.Column(db.Text)
    corrected_text = db.Column(db.Text)
    created_at     = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f'<Feedback {self.original_text} → {self.corrected_text}>'


# ─── NEW: Prescription Storage (cache & reuse) ───────────────

class Prescription(db.Model):
    """Stores extracted prescription data for caching & reuse."""
    __tablename__ = 'prescriptions'

    id             = db.Column(db.String(36), primary_key=True)        # UUID
    image_hash     = db.Column(db.String(64), unique=True, index=True)
    medicines      = db.Column(db.JSON)          # [{name, dosage, frequency, …}]
    doctor_name    = db.Column(db.String(200))
    clinic_address = db.Column(db.Text)
    pincode        = db.Column(db.String(10), index=True)
    raw_result     = db.Column(db.JSON)           # Full analysis result for reuse
    created_at     = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f'<Prescription {self.id[:8]}… meds={len(self.medicines or [])}>'


# ─── NEW: Pharmacy & Inventory (mock / real) ─────────────────

class Pharmacy(db.Model):
    """A pharmacy / medical store."""
    __tablename__ = 'pharmacies'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), nullable=False)
    address    = db.Column(db.Text)
    pincode    = db.Column(db.String(10), index=True, nullable=False)
    phone      = db.Column(db.String(20))
    lat        = db.Column(db.Float)
    lng        = db.Column(db.Float)
    rating     = db.Column(db.Float, default=4.0)
    is_open    = db.Column(db.Boolean, default=True)
    place_id   = db.Column(db.String(100), unique=True, index=True)   # Google Places unique ID
    city       = db.Column(db.String(100))                             # City name for display
    state      = db.Column(db.String(100))                             # State for regional filtering
    source     = db.Column(db.String(20), default='manual')            # 'google' or 'manual'
    types      = db.Column(db.Text)                                    # Google place types (JSON string)
    fetched_at = db.Column(db.DateTime)                                # When data was collected

    def __repr__(self):
        return f'<Pharmacy {self.name}>'


class PharmacyInventory(db.Model):
    """Medicine stock held by a pharmacy."""
    __tablename__ = 'pharmacy_inventory'

    id          = db.Column(db.Integer, primary_key=True)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey('pharmacies.id'), index=True)
    medicine    = db.Column(db.String(150), nullable=False, index=True)  # brand name
    generic     = db.Column(db.String(150))
    in_stock    = db.Column(db.Boolean, default=True)
    price       = db.Column(db.Float)

    pharmacy    = db.relationship('Pharmacy', backref='inventory')

    def __repr__(self):
        return f'<Inventory {self.medicine} @ Pharmacy#{self.pharmacy_id}>'