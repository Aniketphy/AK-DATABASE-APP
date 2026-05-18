# Classification keywords
TRADE_KEYWORDS = [
    "broker", "agent", "realtor", "developer", "builder", "property dealer",
    "real estate", "construction", "landlord", "property manager",
    "realty", "estate agent", "brokerage"
]

SEEKER_KEYWORDS = [
    "looking for", "buy", "rent", "lease", "bhk", "sqft", "carpet area",
    "budget", "possession", "ready to move", "under construction",
    "property type", "2bhk", "3bhk", "1bhk"
]

SOURCE_TYPES = {
    "MSEB": "MSEB consumer data",
    "FACEBOOK": "Facebook ad leads",
    "PROPERTY_PORTAL": "Property portal enquiries",
    "AGENT_LIST": "Broker/agent lists",
    "SCHOOL": "School data",
    "DOCTOR": "Doctor data",
    "POLICE": "Police data",
    "EXPO": "Expo visitor lists",
    "SALES": "Working/sales data",
    "POPULATION": "General population lists"
}

COLUMN_MAPPING = {
    "name": ["name", "full name", "consumer name", "applicant", "customer name", "client name"],
    "mobile": ["mobile", "phone", "contact", "phone number", "cell", "whatsapp"],
    "email": ["email", "e-mail", "email id", "mail"],
    "address": ["address", "residence", "property address", "location"],
    "pincode": ["pincode", "pin", "zip", "postal code"],
    "city": ["city", "town", "locality"],
    "state": ["state", "province"],
    "gender": ["gender", "sex"],
    "age": ["age", "age group", "dob"],
    "income": ["income", "salary", "annual income"]
}
