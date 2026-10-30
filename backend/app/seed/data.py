"""Master data and vocabularies for the demo dataset.

Regional Offices follow AICTE's published list. Every institution, bank, person and instrument generated from these
pools is fictional. Deposit amounts and tenures are illustrative demo values held in an editable table: set them to the
figures in the current Approval Process Handbook.
"""

# code, name, city, address, lat, lon, states
REGIONS = [
    ("WRO", "Western Regional Office", "Mumbai", "Industrial Assurance Bldg., Churchgate, Mumbai 400020",
     18.935, 72.827, ["MH", "GA"]),
    ("VRO", "Regional Office Vadodara", "Vadodara", "Regional Office, Vadodara, Gujarat",
     22.307, 73.181, ["GJ", "DN"]),
    ("SRO", "Southern Regional Office", "Chennai", "Shastri Bhavan, Haddows Road, Nungambakkam, Chennai 600006",
     13.062, 80.243, ["TN", "PY"]),
    ("SWRO", "South Western Regional Office", "Bengaluru", "P.K. Block, Palace Road, Bengaluru 560009",
     12.987, 77.585, ["KA"]),
    ("TVRO", "Regional Office Thiruvananthapuram", "Thiruvananthapuram",
     "College of Engineering campus, Thiruvananthapuram 695016", 8.546, 76.906, ["KL", "LD"]),
    ("CRO", "Central Regional Office", "Bhopal", "Airport Bypass Road, Gandhi Nagar, Bhopal 462036",
     23.287, 77.337, ["MP", "CG"]),
    ("NWRO", "North Western Regional Office", "Chandigarh", "Dakshin Marg, Sector 36-A, Chandigarh 160036",
     30.735, 76.775, ["PB", "HP", "JK", "LA", "CH", "RJ"]),
    ("GRO", "Regional Office Gurugram", "Gurugram", "Regional Office, Gurugram, Haryana",
     28.459, 77.027, ["HR", "DL"]),
    ("NRO", "Northern Regional Office", "Kanpur", "Govt. Polytechnic Campus, Vikas Nagar, Kanpur 208002",
     26.493, 80.315, ["UP", "UK", "BR"]),
    ("ERO", "Eastern Regional Office", "Kolkata", "LB Block, Sector III, Salt Lake City, Kolkata 700098",
     22.573, 88.414, ["WB", "OD", "JH", "SK", "AN"]),
    ("SCRO", "South Central Regional Office", "Hyderabad", "JNTU Masab Tank Campus, Mahaveer Marg, Hyderabad 500028",
     17.401, 78.454, ["TG", "AP"]),
    ("NERO", "North East Regional Office", "Guwahati", "Assam Engineering College Campus, Jalukbari, Guwahati 781013",
     26.150, 91.660, ["AS", "ML", "TR", "MN", "MZ", "NL", "AR"]),
]

STATES = {
    "MH": "Maharashtra", "GA": "Goa", "DN": "Dadra and Nagar Haveli and Daman and Diu", "TN": "Tamil Nadu",
    "PY": "Puducherry", "KA": "Karnataka", "KL": "Kerala", "LD": "Lakshadweep", "MP": "Madhya Pradesh",
    "CG": "Chhattisgarh", "GJ": "Gujarat", "PB": "Punjab", "HR": "Haryana", "HP": "Himachal Pradesh",
    "JK": "Jammu and Kashmir", "LA": "Ladakh", "CH": "Chandigarh", "DL": "Delhi", "RJ": "Rajasthan",
    "UP": "Uttar Pradesh", "UK": "Uttarakhand", "BR": "Bihar", "WB": "West Bengal", "OD": "Odisha",
    "JH": "Jharkhand", "SK": "Sikkim", "AN": "Andaman and Nicobar Islands", "TG": "Telangana",
    "AP": "Andhra Pradesh", "AS": "Assam", "ML": "Meghalaya", "TR": "Tripura", "MN": "Manipur", "MZ": "Mizoram",
    "NL": "Nagaland", "AR": "Arunachal Pradesh",
}

# state: [(city, district, pincode, lat, lon)]
CITIES = {
    "MH": [("Mumbai", "Mumbai Suburban", "400070", 19.07, 72.88), ("Pune", "Pune", "411041", 18.52, 73.86),
           ("Nagpur", "Nagpur", "440013", 21.15, 79.09), ("Nashik", "Nashik", "422003", 20.00, 73.79),
           ("Aurangabad", "Chhatrapati Sambhajinagar", "431005", 19.88, 75.34),
           ("Kolhapur", "Kolhapur", "416004", 16.70, 74.24), ("Solapur", "Solapur", "413002", 17.66, 75.91),
           ("Amravati", "Amravati", "444602", 20.93, 77.75)],
    "GA": [("Panaji", "North Goa", "403001", 15.49, 73.83), ("Margao", "South Goa", "403601", 15.27, 73.96)],
    "DN": [("Silvassa", "Dadra and Nagar Haveli", "396230", 20.27, 73.01)],
    "TN": [("Chennai", "Chennai", "600097", 13.08, 80.27), ("Coimbatore", "Coimbatore", "641014", 11.02, 76.96),
           ("Madurai", "Madurai", "625015", 9.93, 78.12), ("Tiruchirappalli", "Tiruchirappalli", "620015", 10.79, 78.70),
           ("Salem", "Salem", "636011", 11.66, 78.15), ("Tirunelveli", "Tirunelveli", "627011", 8.71, 77.76),
           ("Vellore", "Vellore", "632014", 12.92, 79.13)],
    "PY": [("Puducherry", "Puducherry", "605014", 11.94, 79.81)],
    "KA": [("Bengaluru", "Bengaluru Urban", "560068", 12.97, 77.59), ("Mysuru", "Mysuru", "570006", 12.30, 76.64),
           ("Mangaluru", "Dakshina Kannada", "575025", 12.91, 74.86), ("Hubballi", "Dharwad", "580031", 15.36, 75.12),
           ("Belagavi", "Belagavi", "590008", 15.85, 74.50), ("Kalaburagi", "Kalaburagi", "585102", 17.33, 76.83)],
    "KL": [("Thiruvananthapuram", "Thiruvananthapuram", "695015", 8.52, 76.94), ("Kochi", "Ernakulam", "682022", 9.93, 76.27),
           ("Kozhikode", "Kozhikode", "673601", 11.26, 75.78), ("Thrissur", "Thrissur", "680009", 10.53, 76.21),
           ("Kollam", "Kollam", "691005", 8.89, 76.61)],
    "LD": [("Kavaratti", "Lakshadweep", "682555", 10.57, 72.64)],
    "MP": [("Bhopal", "Bhopal", "462021", 23.26, 77.41), ("Indore", "Indore", "452012", 22.72, 75.86),
           ("Gwalior", "Gwalior", "474005", 26.22, 78.18), ("Jabalpur", "Jabalpur", "482011", 23.18, 79.99),
           ("Ujjain", "Ujjain", "456010", 23.18, 75.78)],
    "CG": [("Raipur", "Raipur", "492010", 21.25, 81.63), ("Bhilai", "Durg", "490020", 21.21, 81.38),
           ("Bilaspur", "Bilaspur", "495009", 22.08, 82.15)],
    "GJ": [("Ahmedabad", "Ahmedabad", "382481", 23.02, 72.57), ("Surat", "Surat", "395007", 21.17, 72.83),
           ("Vadodara", "Vadodara", "390019", 22.31, 73.18), ("Rajkot", "Rajkot", "360005", 22.30, 70.80),
           ("Gandhinagar", "Gandhinagar", "382007", 23.22, 72.65)],
    "PB": [("Ludhiana", "Ludhiana", "141006", 30.90, 75.86), ("Amritsar", "Amritsar", "143105", 31.63, 74.87),
           ("Jalandhar", "Jalandhar", "144022", 31.33, 75.58), ("Patiala", "Patiala", "147004", 30.34, 76.39),
           ("Mohali", "SAS Nagar", "160062", 30.70, 76.72)],
    "HR": [("Gurugram", "Gurugram", "122017", 28.46, 77.03), ("Faridabad", "Faridabad", "121006", 28.41, 77.32),
           ("Kurukshetra", "Kurukshetra", "136119", 29.97, 76.85), ("Hisar", "Hisar", "125005", 29.15, 75.72),
           ("Sonipat", "Sonipat", "131029", 28.99, 77.02)],
    "HP": [("Shimla", "Shimla", "171005", 31.10, 77.17), ("Hamirpur", "Hamirpur", "177005", 31.68, 76.52),
           ("Solan", "Solan", "173229", 30.91, 77.10)],
    "JK": [("Srinagar", "Srinagar", "190006", 34.08, 74.80), ("Jammu", "Jammu", "180011", 32.73, 74.86)],
    "LA": [("Leh", "Leh", "194101", 34.15, 77.58)],
    "CH": [("Chandigarh", "Chandigarh", "160019", 30.73, 76.78)],
    "DL": [("New Delhi", "South Delhi", "110016", 28.55, 77.21), ("Dwarka", "South West Delhi", "110078", 28.59, 77.05),
           ("Rohini", "North West Delhi", "110089", 28.74, 77.12)],
    "RJ": [("Jaipur", "Jaipur", "302022", 26.91, 75.79), ("Jodhpur", "Jodhpur", "342011", 26.24, 73.02),
           ("Udaipur", "Udaipur", "313003", 24.59, 73.71), ("Kota", "Kota", "324005", 25.18, 75.83),
           ("Bikaner", "Bikaner", "334004", 28.02, 73.31), ("Ajmer", "Ajmer", "305004", 26.45, 74.64)],
    "UP": [("Lucknow", "Lucknow", "226028", 26.85, 80.95), ("Kanpur", "Kanpur Nagar", "208016", 26.45, 80.33),
           ("Noida", "Gautam Buddh Nagar", "201310", 28.54, 77.39), ("Ghaziabad", "Ghaziabad", "201009", 28.67, 77.45),
           ("Agra", "Agra", "282007", 27.18, 78.01), ("Varanasi", "Varanasi", "221005", 25.32, 82.97),
           ("Prayagraj", "Prayagraj", "211004", 25.44, 81.85), ("Meerut", "Meerut", "250005", 28.98, 77.71),
           ("Gorakhpur", "Gorakhpur", "273010", 26.76, 83.37)],
    "UK": [("Dehradun", "Dehradun", "248007", 30.32, 78.03), ("Haridwar", "Haridwar", "249404", 29.95, 78.16),
           ("Roorkee", "Haridwar", "247667", 29.87, 77.89)],
    "BR": [("Patna", "Patna", "800013", 25.59, 85.14), ("Gaya", "Gaya", "823001", 24.79, 85.00),
           ("Muzaffarpur", "Muzaffarpur", "842003", 26.12, 85.39)],
    "WB": [("Kolkata", "Kolkata", "700091", 22.57, 88.36), ("Durgapur", "Paschim Bardhaman", "713209", 23.55, 87.32),
           ("Siliguri", "Darjeeling", "734010", 26.73, 88.40), ("Howrah", "Howrah", "711103", 22.59, 88.31)],
    "OD": [("Bhubaneswar", "Khordha", "751024", 20.30, 85.82), ("Cuttack", "Cuttack", "753008", 20.46, 85.88),
           ("Rourkela", "Sundargarh", "769008", 22.26, 84.85)],
    "JH": [("Ranchi", "Ranchi", "834004", 23.34, 85.31), ("Jamshedpur", "East Singhbhum", "831014", 22.80, 86.20),
           ("Dhanbad", "Dhanbad", "826004", 23.80, 86.43)],
    "SK": [("Gangtok", "Gangtok", "737102", 27.33, 88.61)],
    "AN": [("Sri Vijaya Puram", "South Andaman", "744103", 11.62, 92.73)],
    "TG": [("Hyderabad", "Hyderabad", "500085", 17.39, 78.49), ("Warangal", "Hanamkonda", "506015", 17.98, 79.59),
           ("Karimnagar", "Karimnagar", "505001", 18.44, 79.13), ("Medchal", "Medchal-Malkajgiri", "501401", 17.63, 78.48)],
    "AP": [("Visakhapatnam", "Visakhapatnam", "530048", 17.69, 83.22), ("Vijayawada", "NTR", "520007", 16.51, 80.65),
           ("Guntur", "Guntur", "522510", 16.31, 80.44), ("Tirupati", "Tirupati", "517502", 13.63, 79.42),
           ("Kakinada", "Kakinada", "533003", 16.99, 82.25), ("Nellore", "Nellore", "524004", 14.44, 79.99)],
    "AS": [("Guwahati", "Kamrup Metropolitan", "781013", 26.14, 91.74), ("Jorhat", "Jorhat", "785001", 26.75, 94.20),
           ("Silchar", "Cachar", "788010", 24.83, 92.78)],
    "ML": [("Shillong", "East Khasi Hills", "793003", 25.58, 91.89)],
    "TR": [("Agartala", "West Tripura", "799046", 23.83, 91.29)],
    "MN": [("Imphal", "Imphal West", "795004", 24.82, 93.94)],
    "MZ": [("Aizawl", "Aizawl", "796012", 23.73, 92.72)],
    "NL": [("Dimapur", "Chümoukedima", "797112", 25.86, 93.73)],
    "AR": [("Itanagar", "Papum Pare", "791113", 27.08, 93.61)],
}

# Rough share of AICTE-approved institutions by state, used to spread the fictional ones.
STATE_WEIGHTS = {
    "MH": 14, "TN": 11, "UP": 10, "KA": 7, "AP": 7, "TG": 6, "MP": 5, "RJ": 4, "GJ": 5, "HR": 3, "PB": 3,
    "WB": 3, "KL": 3, "OD": 2, "BR": 1.5, "JH": 1, "CG": 1.2, "UK": 1, "DL": 1.2, "HP": 0.6, "JK": 0.5, "GA": 0.4,
    "AS": 0.6, "CH": 0.3, "PY": 0.3, "ML": 0.1, "TR": 0.1, "MN": 0.1, "MZ": 0.05, "NL": 0.05, "AR": 0.05,
    "SK": 0.05, "AN": 0.03, "DN": 0.05, "LA": 0.02, "LD": 0.01,
}

# code, name, type, region code (for ROs), description
UNITS = [
    ("RB", "Regulation Bureau", "BUREAU", None,
     "Scrutiny, verification and custody of security deposits and FDRs lodged by institutions."),
    ("FIN", "Finance & Accounts Division", "FINANCE", None, "Lien release, refunds and reconciliation."),
    ("AB", "Approval Bureau", "BUREAU", None, "Approval, extension of approval and closure of institutions."),
    ("MGMT", "Office of the Member Secretary", "MANAGEMENT", None, "Competent authority for release of deposits."),
] + [
    (f"RO-{code}", name if city in name else f"{name}, {city}", "REGIONAL_OFFICE", code,
     f"AICTE {name}" + ("" if city in name else f" at {city}") + ".")
    for code, name, city, *_ in REGIONS
]

# Fictional banks. code (IFSC prefix), name, short name, sector, verification channel, scheduled?, aliases
BANKS = [
    ("BHRT", "Bharat National Bank", "BNB", "PUBLIC", "GATEWAY", True, ["Bharat Natl Bank", "BNB"]),
    ("UNKB", "Union Kisan Bank", "UKB", "PUBLIC", "GATEWAY", True, ["Union Kisan", "UKB"]),
    ("HMLB", "Himalaya Bank", "Himalaya", "PUBLIC", "GATEWAY", True, ["Himalaya Bank Ltd"]),
    ("SNDB", "Sindhu Bank", "Sindhu", "PUBLIC", "LETTER", True, ["Sindhu Bank Ltd"]),
    ("SHYB", "Sahyadri Bank", "Sahyadri", "PUBLIC", "LETTER", True, ["Sahyadri Bank of India"]),
    ("VNDB", "Vindhya Bank", "Vindhya", "PRIVATE", "GATEWAY", True, ["Vindhya Bank Ltd"]),
    ("NRMB", "Narmada Commercial Bank", "Narmada", "PRIVATE", "GATEWAY", True, ["Narmada Bank", "NCB"]),
    ("KVRB", "Kaveri Bank", "Kaveri", "PRIVATE", "LETTER", True, ["Kaveri Bank Ltd"]),
    ("TPTB", "Tapti Bank", "Tapti", "PRIVATE", "GATEWAY", True, ["Tapti Bank Ltd"]),
    ("PRVB", "Purvanchal Small Finance Bank", "Purvanchal SFB", "SMALL_FINANCE", "LETTER", True, ["Purvanchal SFB"]),
    ("DCNB", "Deccan Urban Co-operative Bank", "Deccan Urban", "COOPERATIVE", "LETTER", False, ["Deccan Co-op Bank"]),
]
BANK_WEIGHTS = {"BHRT": 26, "UNKB": 14, "HMLB": 9, "SNDB": 8, "SHYB": 9, "VNDB": 10, "NRMB": 8, "KVRB": 6,
                "TPTB": 6, "PRVB": 3, "DCNB": 1}
BRANCH_AREAS = ["Main Branch", "Station Road", "Civil Lines", "MG Road", "Industrial Area", "Collectorate",
                "Camp Area", "University Road", "Market Yard", "Cantonment"]

# purpose, institution type ("*" = any), amount (Rs), minimum tenure (months), note. Illustrative demo values.
DEPOSIT_RULES = [
    ("NEW_INSTITUTION", "Engineering & Technology", 1_500_000, 60, "Demo value; set per the current handbook."),
    ("NEW_INSTITUTION", "Management", 1_000_000, 60, "Demo value; set per the current handbook."),
    ("NEW_INSTITUTION", "Pharmacy", 1_000_000, 60, "Demo value; set per the current handbook."),
    ("NEW_INSTITUTION", "Diploma (Polytechnic)", 500_000, 60, "Demo value; set per the current handbook."),
    ("NEW_INSTITUTION", "*", 750_000, 60, "Demo value; set per the current handbook."),
    ("NEW_PROGRAMME", "*", 500_000, 36, "Demo value; set per the current handbook."),
    ("INTAKE_INCREASE", "*", 300_000, 36, "Demo value; set per the current handbook."),
    ("OTHER", "*", 300_000, 36, "Demo value; set per the current handbook."),
]

SOCIETY_FORMS = ["Education Society", "Shikshan Prasarak Mandal", "Educational Trust", "Vidya Pratishthan",
                 "Charitable Trust", "Shiksha Samiti", "Education Foundation"]

# Fictional institution name roots.
NAME_ROOTS = [
    "Abhyudaya", "Agastya", "Akshar", "Amaltas", "Anantam", "Anvesha", "Aparajita", "Arunodaya", "Ashwattha",
    "Atharva", "Bodhi", "Chaitanya", "Chinar", "Deodar", "Devashree", "Dhruva", "Divyajyoti", "Ekalavya",
    "Gandhar", "Gyanodaya", "Gyanpeeth", "Himadri", "Jagriti", "Jyotirmay", "Kadamb", "Kalpataru", "Kanchan",
    "Kaustubh", "Keshav", "Kirti", "Kshitij", "Madhuban", "Mahima", "Manthan", "Medhavi", "Meghdoot", "Mrinal",
    "Nachiketa", "Navchetna", "Neelkanth", "Nirmiti", "Nishchay", "Padmavati", "Palash", "Pragyan", "Prabodhan",
    "Prerana", "Pushpak", "Rashmi", "Ratnadeep", "Riddhi", "Sahyog", "Samarth", "Sankalp", "Sanskriti",
    "Saptarishi", "Sarthak", "Shaurya", "Shikhar", "Shirish", "Shraddha", "Siddhant", "Sindhuja", "Srijan",
    "Sudarshan", "Suryodaya", "Swarnim", "Tapasya", "Tejas", "Trayambak", "Tulsi", "Udaan", "Udayagiri",
    "Unnati", "Utkarsh", "Vaibhav", "Vardhaman", "Varenya", "Vasundhara", "Vedanta", "Vidyadeep", "Vidyasagar",
    "Vihaan", "Vinayaka", "Vishwakarma", "Vriksha", "Yashaswi", "Yugantar", "Aarohan", "Abhinav", "Adarsh",
    "Akanksha", "Ananya", "Anugraha", "Archana", "Ashadeep", "Avishkar", "Chetana", "Darpan", "Deepshikha",
    "Dhanvantari", "Gaurav", "Hemant", "Indradhanush", "Jeevandeep", "Kalindi", "Kamakhya", "Kanak", "Kaveri Valley",
    "Lakshya", "Malhar", "Manasa", "Mangalam", "Navya", "Nilachal", "Ojas", "Parijat", "Pratibha", "Purvanchal",
    "Rajhans", "Saraswat", "Satpuda", "Shubham", "Sunrise Valley", "Tarang", "Trinetra", "Ujjwal", "Vindhyachal",
]
FOUNDER_FIRST = ["Ramdas", "Govind", "Shankarrao", "Laxman", "Hariprasad", "Sitaram", "Bhaskar", "Madhavrao",
                 "Prabhakar", "Raghunath", "Venkataramana", "Narayan", "Anandrao", "Kesavan", "Gopinath", "Durgadas"]
FOUNDER_LAST = ["Kulkarni", "Deshpande", "Patil", "Reddy", "Naidu", "Iyer", "Pillai", "Sharma", "Verma", "Mishra",
                "Tiwari", "Chauhan", "Rathore", "Banerjee", "Ghosh", "Mohanty", "Barua", "Gill", "Sandhu", "Joshi"]

INST_TYPES = [
    ("Engineering & Technology", 46, ["Institute of Technology", "College of Engineering",
                                      "Institute of Engineering & Technology", "College of Engineering & Technology",
                                      "Engineering College", "Institute of Technology & Science"], (180, 1200)),
    ("Management", 19, ["Institute of Management", "Institute of Management Studies",
                        "School of Business Management", "Institute of Business Administration"], (60, 300)),
    ("Pharmacy", 15, ["College of Pharmacy", "Institute of Pharmaceutical Sciences", "Pharmacy College"], (60, 200)),
    ("Diploma (Polytechnic)", 12, ["Polytechnic", "Polytechnic College", "Institute of Diploma Studies"], (120, 600)),
    ("Architecture", 3, ["School of Architecture", "College of Architecture"], (40, 120)),
    ("Computer Applications", 3, ["Institute of Computer Applications"], (60, 180)),
    ("Hotel Management & Catering", 2, ["Institute of Hotel Management & Catering Technology"], (60, 240)),
]
OWNERSHIP = [("Private (Self-financing)", 78), ("Government-aided", 10), ("University-managed", 7),
             ("Deemed to be University", 5)]

PERSON_FIRST = [
    "Aarav", "Aditi", "Akash", "Ananya", "Anjali", "Arjun", "Ayesha", "Bhavna", "Chetan", "Deepak", "Divya",
    "Farhan", "Gaurav", "Harsh", "Ishita", "Jaspreet", "Karan", "Kavya", "Lakshmi", "Manish", "Meera", "Mohit",
    "Neha", "Nikhil", "Pooja", "Pranav", "Priya", "Rahul", "Rakesh", "Riya", "Rohan", "Sakshi", "Sameer",
    "Sandeep", "Shreya", "Siddharth", "Sneha", "Suresh", "Tanvi", "Tarun", "Uday", "Varun", "Vikas", "Yash",
    "Zoya", "Abdul", "Fatima", "Gurpreet", "Lalremruati", "Tenzin", "Bijoy", "Kalpana", "Murugan", "Selvi",
]
PERSON_LAST = [
    "Sharma", "Verma", "Patil", "Deshmukh", "Reddy", "Naidu", "Iyer", "Nair", "Menon", "Pillai", "Gupta",
    "Agarwal", "Singh", "Kaur", "Yadav", "Khan", "Ansari", "Das", "Ghosh", "Mukherjee", "Mohanty", "Behera",
    "Barua", "Bora", "Sangma", "Jain", "Shah", "Mehta", "Chauhan", "Rathore", "Kumar", "Mishra", "Tiwari",
    "Pandey", "Joshi", "Kulkarni", "Shetty", "Rao", "Hegde", "Thomas", "Fernandes", "D'Souza",
]

