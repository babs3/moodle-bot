# Banco de dados de Q&A mapeado diretamente dos PDFs fornecidos
qa_bank = [
    {
        "pdf": "SCI_2425_00.pdf",
        "qa": [
            ("What is the acronym and course code for Cyber-Physical Systems and Internet of Things?", "The course code is M.EIC043 and the acronym is SCI."),
            ("What is the continuous assessment weight in the final grade formula?", "The continuous assessment has a weight of 40%, while the practical project accounts for 45% and the seminar for 15%."),
            ("What hardware is available in the laboratory for the SCI practical project?", "Students have access to Arduino Nano 33 IoT, DFRobot KIT0011 (with distance, light, gas, and vibration sensors), and Raspberry Pi boards."),
            ("What are the main milestones for the project evaluation?", "The milestones are the Initial Concept Presentation on October 7th, the Logbook review on January 6th, and the Final Presentation and Report on January 13th."),
            ("What minimum grade is required in the interim exams to avoid failing continuous evaluation?", "Students must achieve a minimum of 40% in every interim exam and an overall continuous assessment average of at least 50%.")
        ]
    },
    {
        "pdf": "SCI_2425_01.pdf",
        "qa": [
            ("Explain the concept of a Cyber-Physical System according to the course overview.", "A CPS consists of a collection of computing devices communicating with one another and interacting with the physical world via sensors and actuators in a feedback loop."),
            ("What are the four layers defined in the 5-Layer IoT Architecture graph?", "The layers are the Perception Layer (Data gathering), Network Layer (Transmission), Middleware Layer (Analytics and cloud processing), and Application/Business Layer."),
            ("What is the focus of the 5C CPS Architecture proposed by Jay Lee?", "It focuses on a structured development through 5 levels: Smart Connection, Data-to-Information Conversion, Cyber (Digital Twin), Cognition, and Configuration (Self-adaptation)."),
            ("How do IoT and CPS differ in terms of their historical lineage?", "CPS emerged primarily from a systems engineering and control perspective focusing on physical processes, whereas IoT emerged from a networking and IT perspective aiming to extend the internet into everyday objects."),
            ("What are Smart Objects within the context of the IoT evolution timeline?", "Smart Objects are interactive things that possess embedded analytical and processing capabilities to autonomously act on data obtained from their environment.")
        ]
    },
    {
        "pdf": "SCI_2425_02.pdf",
        "qa": [
            ("How does predictive maintenance differ from preventive maintenance?", "Preventive maintenance happens at fixed regular intervals, whereas predictive maintenance monitors condition markers in real-time to predict exactly when a component will break."),
            ("What is a Digital Twin and give an example of its application?", "A Digital Twin is a virtual representation that serves as a real-time digital counterpart of a physical object or process, widely used for failure diagnosis and performance optimization."),
            ("Differentiate between a Digital Model, a Digital Shadow, and a Digital Twin.", "In a Digital Model, data flow is manual. In a Digital Shadow, data flows automatically from physical to digital. In a Digital Twin, the data flow is fully automated and bidirectional."),
            ("What are the characteristics of an Operational Dashboard in Grafana?", "Operational dashboards show short timeframes and operational metrics updating in real-time, focusing heavily on daily metrics."),
            ("How can machine learning be used for quality control on a production floor?", "By integrating machine learning with continuous sensor streams, the system can perform real-time anomaly detection and evaluate product quality at each production phase rather than just at the end.")
        ]
    },
    {
        "pdf": "SCI_2425_03.pdf",
        "qa": [
            ("Why is UDP often prioritized over TCP in constrained IoT applications?", "UDP is preferred when low latency is a priority over reliability because it lacks the heavy connection management overhead of TCP, helping save power on restricted edge devices."),
            ("Describe the core communication model used by MQTT.", "MQTT uses a broker-centric publish-subscribe messaging model where clients publish data to specific topics and subscribers listen to those topics via a central broker."),
            ("What is OPC UA and why is it used in industrial automation environments?", "OPC UA is an open-source, highly secure interoperable protocol used to bridge field-level device communication (PLCs, sensors) straight into MES, ERP, or cloud applications securely."),
            ("What application layer protocol allows IPv6 packets to be compressed over low-power wireless personal networks?", "The protocol is 6LoWPAN, which adapts IPv6 header requirements to fit resource-constrained link-layer systems like IEEE 802.15.4."),
            ("Compare CoAP and MQTT in terms of architecture design choices.", "MQTT requires a central broker for its publish-subscribe mechanism, while CoAP is a lightweight, binary RESTful protocol designed for request-response interactions mirroring traditional HTTP but over UDP.")
        ]
    },
    {
        "pdf": "SCI_2425_04.pdf",
        "qa": [
            ("What are the primary functional requirements of an IoT middleware platform?", "The primary functional requirements include Resource Discovery, Resource Management, Data Management, Event Management, and Code Management (remote firmware updates)."),
            ("List three publicly traded IoT middleware platforms mentioned in the slides.", "Examples include AWS IoT Core, Microsoft Azure IoT Hub, Google Cloud IoT Platform, and IBM Watson IoT."),
            ("What non-functional requirement ensures an IoT system stays operational during partial node failures?", "Availability, which requires the platform to implement failover mechanisms to support critical infrastructure even during physical disturbances."),
            ("How does middleware solve the issue of data heterogeneity in multi-vendor environments?", "It provides device abstraction layers, semantic data models, and protocol ontologies that normalize raw multi-vendor payloads into consistent data formats."),
            ("What is an End-to-End connectivity middleware platform?", "It is a platform tightly integrated with proprietary vendor hardware, designed to supply an immediate out-of-the-box hardware-to-cloud solution, such as Samsara or Particle Cloud.")
        ]
    },
    {
        "pdf": "SCI_2425_05_copia.pdf",
        "qa": [
            ("What are the elements that compose the definition of Dependability?", "Dependability encompasses Reliability (consistency without error), Availability (readiness when requested), and Maintainability (ease of repairs or updates)."),
            ("What security lesson was learned from the 2018 Strava military base fitness tracker incident?", "The incident highlighted severe privacy vulnerabilities where aggregating anonymized public heatmap data inadvertently mapped out hidden guard patrols and perimeters of remote military installations."),
            ("List four top privacy-enhancing measures that should be integrated into a CPS system design.", "Key measures include Data Collection Limitation, Informed User Consent, Data Minimization, Data Anonymization, and strict Data Retention Policies."),
            ("What percentage of tested IoT devices failed to enforce complex password lengths according to data metrics?", "Eighty percent (80%) of early consumer IoT devices failed to require passwords of sufficient cryptographic length and complexity."),
            ("What risks does unencrypted network communication present to critical industrial control systems?", "It exposes the communication link to passive eavesdropping and man-in-the-middle injection attacks, potentially allowing attackers to issue unauthorized commands to actuators or manipulate physical processes.")
        ]
    },
    {
        "pdf": "SCI_2324_06 (EN).pdf",
        "qa": [
            ("What architecture was proposed within the RECLAIM EU project toolkit for refurbishment planning?", "The architecture integrates a Trend Analyzer, Alarm Modules, F-messaging APIs, and Grafana visualization boards completely containerized within Docker environments."),
            ("What machine data anomalies were monitored in the PODIUM shoemaking case study?", "The system tracked structural errors, cycle param deviations, and axis servo link errors generated by macro parameters."),
            ("What real-time process parameters were collected in the friction welding demonstration case?", "The data monitored included bearing states (motor/spindle), ambient temperatures, duration, velocity averages, and mean forces exerted during joining phases."),
            ("How does the RECLAIM framework support the concept of a Circular Economy?", "By implementing digital retrofitting infrastructure and prognostic health toolkits, it extends the design life of aging factory assets approaching their designer lifetime limit."),
            ("What open data architecture does the RECLAIM toolkit use to exchange real-time machine states?", "It leverages OPC UA server structures paired with real-time JSON parsers and Python data collection modules.")
        ]
    }
]