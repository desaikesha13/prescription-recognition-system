from db import db


class Medicine(db.Model):
    __tablename__ = 'medicines'

    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(150), nullable=False, index=True)
    generic = db.Column(db.String(200), nullable=False, index=True)
    category = db.Column(db.String(100), nullable=False, index=True)

    manufacturer = db.Column(db.String(200))
    dosage_forms = db.Column(db.Text)
    strengths = db.Column(db.Text)
    schedule = db.Column(db.String(10))
    is_otc = db.Column(db.Boolean, default=False)
    description = db.Column(db.Text)
    side_effects = db.Column(db.Text)
    typical_dosage = db.Column(db.String(200))
    avg_price = db.Column(db.Float)
    active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now()
    )

    synonyms = db.relationship('MedicineSynonym', backref='medicine', lazy='dynamic')
    interactions = db.relationship(
        'DrugInteraction',
        foreign_keys='DrugInteraction.medicine_id',
        backref='medicine',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<Medicine {self.brand}>'


class MedicineSynonym(db.Model):
    __tablename__ = 'medicine_synonyms'

    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(
        db.Integer,
        db.ForeignKey('medicines.id'),
        nullable=False,
        index=True
    )
    synonym = db.Column(db.String(200), nullable=False, index=True)
    synonym_type = db.Column(db.String(30))

    def __repr__(self):
        return f'<Synonym {self.synonym} → Medicine#{self.medicine_id}>'


class DrugInteraction(db.Model):
    __tablename__ = 'drug_interactions'

    id = db.Column(db.Integer, primary_key=True)
    medicine_id = db.Column(
        db.Integer,
        db.ForeignKey('medicines.id'),
        nullable=False,
        index=True
    )
    interacts_with_id = db.Column(
        db.Integer,
        db.ForeignKey('medicines.id'),
        nullable=False,
        index=True
    )
    severity = db.Column(db.String(20))
    description = db.Column(db.Text)
    clinical_note = db.Column(db.Text)

    interacts_with = db.relationship('Medicine', foreign_keys=[interacts_with_id])

    def __repr__(self):
        return f'<Interaction Med#{self.medicine_id} ↔ Med#{self.interacts_with_id}>'


class Feedback(db.Model):
    __tablename__ = 'feedback'

    id = db.Column(db.Integer, primary_key=True)
    image_hash = db.Column(db.Text, index=True)
    original_text = db.Column(db.Text)
    corrected_text = db.Column(db.Text)
    feedback_type = db.Column(db.String(20), default='correction')
    api_confidence = db.Column(db.String(10))
    db_similarity = db.Column(db.Float)
    used_in_training = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f'<Feedback {self.original_text} → {self.corrected_text}>'


class Prescription(db.Model):
    __tablename__ = 'prescriptions'

    id = db.Column(db.String(36), primary_key=True)
    image_hash = db.Column(db.String(64), unique=True, index=True)
    medicines = db.Column(db.JSON)
    doctor_name = db.Column(db.String(200))
    clinic_address = db.Column(db.Text)
    pincode = db.Column(db.String(10), index=True)
    raw_result = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f'<Prescription {self.id[:8]}… meds={len(self.medicines or [])}>'


class Pharmacy(db.Model):
    __tablename__ = 'pharmacies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text)
    pincode = db.Column(db.String(10), index=True, nullable=False)
    phone = db.Column(db.String(20))
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    rating = db.Column(db.Float, default=4.0)
    is_open = db.Column(db.Boolean, default=True)
    place_id = db.Column(db.String(100), unique=True, index=True)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    source = db.Column(db.String(20), default='manual')
    types = db.Column(db.Text)
    fetched_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Pharmacy {self.name}>'


class PharmacyInventory(db.Model):
    __tablename__ = 'pharmacy_inventory'

    id = db.Column(db.Integer, primary_key=True)
    pharmacy_id = db.Column(db.Integer, db.ForeignKey('pharmacies.id'), index=True)
    medicine = db.Column(db.String(150), nullable=False, index=True)
    generic = db.Column(db.String(150))
    in_stock = db.Column(db.Boolean, default=True)
    price = db.Column(db.Float)

    pharmacy = db.relationship('Pharmacy', backref='inventory')

    def __repr__(self):
        return f'<Inventory {self.medicine} @ Pharmacy#{self.pharmacy_id}>'
