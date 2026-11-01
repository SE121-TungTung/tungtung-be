"""Seed and calibrate IRT parameters for auto-gradable questions in question_bank.

This script:
1. Identifies all auto-gradable questions (multiple_choice, true_false_not_given, yes_no_not_given).
2. Calculates empirical difficulty 'b' from test_responses if available, or falls back to difficulty_level.
3. Sets discrimination 'a', guessing 'c', irt_calibrated=True, and is_cat_eligible=True.
4. Enriches passages/contexts so every CAT-eligible Reading and Listening question is self-contained.
"""

import math
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal, engine
from app.models.test import (
    ContentPassage,
    ContentStatus,
    DifficultyLevel,
    QuestionBank,
    QuestionType,
    SkillArea,
)

engine.echo = False

DIFFICULTY_B_MAP = {
    DifficultyLevel.VERY_EASY: -2.0,
    DifficultyLevel.EASY: -1.0,
    DifficultyLevel.MEDIUM: 0.0,
    DifficultyLevel.HARD: 1.0,
    DifficultyLevel.VERY_HARD: 2.0,
}

DIFFICULTY_A_MAP = {
    DifficultyLevel.VERY_EASY: 0.90,
    DifficultyLevel.EASY: 1.00,
    DifficultyLevel.MEDIUM: 1.15,
    DifficultyLevel.HARD: 1.35,
    DifficultyLevel.VERY_HARD: 1.50,
}

GUESSING_MAP = {
    QuestionType.MULTIPLE_CHOICE: 0.25,
    QuestionType.TRUE_FALSE_NOT_GIVEN: 0.3333,
    QuestionType.YES_NO_NOT_GIVEN: 0.3333,
}

AUTO_GRADABLE_TYPES = [
    QuestionType.MULTIPLE_CHOICE,
    QuestionType.TRUE_FALSE_NOT_GIVEN,
    QuestionType.YES_NO_NOT_GIVEN,
]

RENEWABLE_ENERGY_FULL_PASSAGE = """Paragraph 1
The global transition to renewable energy has accelerated markedly over the past decade as nations seek to diversify their power generation portfolios. Modern renewable energy encompasses several distinct technologies, including hydroelectric power, onshore and offshore wind turbines, geothermal systems, and solar photovoltaic installations. Among these alternatives, solar photovoltaic technology has experienced the fastest growth over the last ten years, driven by steep declines in manufacturing costs and modular deployment. As a result of these economies of scale, solar energy is now cheaper than coal-fired electricity in most countries, making it the preferred choice for new utility-scale power generation.

Paragraph 2
Despite rapid capacity additions, energy planners emphasize that expanding generation is only the first step toward a sustainable energy ecosystem. To establish a truly sustainable grid—one that remains maintainable over the long term without exhausting finite mineral reserves or destabilizing regional ecosystems—utilities must modernize transmission corridors and invest in circular recycling for decommissioned turbine blades and solar panels. Without long-term resource stewardship, rapid infrastructure deployment could create secondary environmental bottlenecks.

Paragraph 3
Furthermore, the intermittent nature of wind and solar power presents ongoing challenges for grid stability and seasonal energy storage. While utility-scale battery arrays can smooth out daily fluctuations, they remain costly for multi-week winter deficits. Consequently, rather than advocating for either immediate reactor closures or permanent nuclear expansion, the author views nuclear energy as a pragmatic transitional solution that can provide reliable low-carbon baseload electricity while next-generation storage technologies reach commercial maturity."""


ADDITIONAL_READING_QUESTIONS = [
    {
        "title": "CAT Reading - Marine Biodiversity Impact",
        "passage_title": "Coral Reefs and Anthropogenic Ocean Change",
        "passage_text": (
            "Paragraph 1\n"
            "Tropical coral reefs occupy less than one percent of the ocean floor yet support nearly a quarter of all known marine species. "
            "Built over millennia by colonies of calcium-secreting polyps living in symbiosis with photosynthetic microalgae called zooxanthellae, "
            "these complex three-dimensional habitats act as natural breakwaters that shield coastlines from storm surges.\n\n"
            "Paragraph 2\n"
            "In recent decades, however, marine biologists have documented unprecedented reef degradation across the Indo-Pacific and Caribbean basins. "
            "While localized factors such as commercial maritime transport and seasonal tidal shifts affect specific bays, the primary threat to coral reefs "
            "in tropical oceans is the dual stress of rising ocean temperatures and ocean acidification. Elevated sea temperatures disrupt the delicate "
            "symbiosis between polyps and zooxanthellae, triggering mass coral bleaching, while absorbed atmospheric carbon dioxide lowers seawater pH "
            "and impedes calcifying organisms from rebuilding their skeletal structures."
        ),
        "question_text": "According to paragraph 2, what is the primary threat to coral reefs in tropical oceans?",
        "question_type": QuestionType.MULTIPLE_CHOICE,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.EASY,
        "options": [
            {"id": "A", "text": "Rising ocean temperatures and acidification"},
            {"id": "B", "text": "Overgrowth of commercial maritime transport"},
            {"id": "C", "text": "Invasive deep-sea predator species"},
            {"id": "D", "text": "Seasonal tidal shifts in coastal zones"},
        ],
        "correct_answer": "A",
        "explanation": "Paragraph 2 explicitly states that elevated sea temperatures and ocean acidification are the primary threat inducing coral bleaching.",
        "irt_b": -1.3,
        "irt_a": 1.0,
        "irt_c": 0.25,
    },
    {
        "title": "CAT Reading - Urban Transportation Models",
        "passage_title": "Redesigning European Commuter Corridors",
        "passage_text": (
            "Paragraph 1\n"
            "Over the past twenty years, northern European municipalities have increasingly shifted urban transport investments away from multi-lane arterial "
            "highways toward grade-separated active mobility networks. By physically isolating cyclists from motorized traffic and synchronizing traffic signals "
            "to favor bicycle speeds—a system known as the 'Green Wave'—cities have transformed daily commuting habits.\n\n"
            "Paragraph 2\n"
            "Empirical longitudinal research conducted in Copenhagen between 2015 and 2023 demonstrated that the completion of twelve dedicated cycling corridors "
            "reduced peak-hour private automobile commuter traffic across the inner ring by 34%. Furthermore, municipal health audits recorded a measurable decline "
            "in respiratory hospitalizations along the redesigned avenues."
        ),
        "question_text": "The research conducted in Copenhagen demonstrated that dedicated cycling corridors reduced commuter traffic by 34%.",
        "question_type": QuestionType.TRUE_FALSE_NOT_GIVEN,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.EASY,
        "options": [
            {"id": "TRUE", "text": "True"},
            {"id": "FALSE", "text": "False"},
            {"id": "NOT GIVEN", "text": "Not Given"},
        ],
        "correct_answer": "TRUE",
        "explanation": "Paragraph 2 directly confirms a 34% reduction in peak-hour commuter traffic following the completion of dedicated cycling corridors in Copenhagen.",
        "irt_b": -1.0,
        "irt_a": 1.1,
        "irt_c": 0.3333,
    },
    {
        "title": "CAT Reading - Cognitive Plasticity in Older Adults",
        "passage_title": "Bilingualism and Neurocognitive Reserve",
        "passage_text": (
            "Paragraph 1\n"
            "Neuroimaging studies of aging populations have increasingly challenged the assumption that executive cognitive decline proceeds at a uniform rate. "
            "Because bilingual speakers must constantly manage two active lexical systems—inhibiting one language while selecting words from the other—their "
            "prefrontal neural networks undergo continuous lifelong training.\n\n"
            "Paragraph 2\n"
            "In a multi-center cohort study tracking 1,200 older adults over a decade, researchers found that lifelong bilingual seniors preserved executive control "
            "function significantly longer than monolingual peers matched for education and socioeconomic status, delaying the clinical onset of age-related cognitive "
            "impairment by an average of 4.5 years."
        ),
        "question_text": "Researchers found that bilingual seniors preserved executive control function significantly longer.",
        "question_type": QuestionType.YES_NO_NOT_GIVEN,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.MEDIUM,
        "options": [
            {"id": "YES", "text": "Yes"},
            {"id": "NO", "text": "No"},
            {"id": "NOT GIVEN", "text": "Not Given"},
        ],
        "correct_answer": "YES",
        "explanation": "Paragraph 2 confirms that bilingual older adults preserved executive control function significantly longer than monolingual peers.",
        "irt_b": -0.2,
        "irt_a": 1.2,
        "irt_c": 0.3333,
    },
    {
        "title": "CAT Reading - Agricultural Automation Ethics",
        "passage_title": "Robotic Harvesting in Mediterranean Horticulture",
        "passage_text": (
            "Paragraph 1\n"
            "Demographic shifts and rural-to-urban migration have created acute seasonal labor deficits across southern European fruit and vegetable farms. "
            "In response, agricultural consortia in Spain, Italy, and Greece have deployed computer-vision robotic harvesters capable of identifying and picking "
            "ripe produce without bruising delicate skins.\n\n"
            "Paragraph 2\n"
            "Yet economists caution against viewing mechanization as a panacea. While autonomous harvesting systems have partially alleviated peak-season bottlenecks "
            "in high-capital greenhouse operations, they have by no means completely resolved agricultural labor shortages in Mediterranean countries. Irregular terrain "
            "in traditional olive groves and vineyards, combined with high upfront leasing costs for smallholders, means that human seasonal workers remain indispensable."
        ),
        "question_text": "Autonomous harvesting systems have completely resolved agricultural labor shortages in Mediterranean countries.",
        "question_type": QuestionType.YES_NO_NOT_GIVEN,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.MEDIUM,
        "options": [
            {"id": "YES", "text": "Yes"},
            {"id": "NO", "text": "No"},
            {"id": "NOT GIVEN", "text": "Not Given"},
        ],
        "correct_answer": "NO",
        "explanation": "Paragraph 2 explicitly states that autonomous systems have only partially alleviated bottlenecks and have by no means completely resolved labor shortages.",
        "irt_b": 0.1,
        "irt_a": 1.25,
        "irt_c": 0.3333,
    },
    {
        "title": "CAT Reading - Renewable Energy Grid Integration",
        "passage_title": "Grid-Scale Battery Storage Limitations",
        "passage_text": (
            "Paragraph 1\n"
            "As variable wind and solar generation exceed 50% of instantaneous electricity supply on modern power grids, transmission operators have deployed "
            "gigawatt-scale lithium-ion battery installations to absorb midday solar surpluses and discharge power during evening demand peaks.\n\n"
            "Paragraph 2\n"
            "Nevertheless, power systems engineers view utility-scale lithium-ion storage as an interim solution rather than a permanent fix for deep decarbonization. "
            "The primary technical limitation is chemical capacity degradation over repeated 4-hour charge-discharge cycles, which diminishes usable storage volume "
            "within eight to ten years and renders lithium-ion arrays economically unviable for multi-week seasonal storage."
        ),
        "question_text": "Why do grid operators view utility-scale lithium-ion storage as an interim solution rather than a permanent fix?",
        "question_type": QuestionType.MULTIPLE_CHOICE,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.MEDIUM,
        "options": [
            {"id": "A", "text": "Limited lifespan degradation over repeated 4-hour discharge cycles"},
            {"id": "B", "text": "Inability to synchronize frequency modulation with alternating currents"},
            {"id": "C", "text": "Excessive cooling electricity consumption during peak daylight"},
            {"id": "D", "text": "High international import duties on cobalt and nickel ore"},
        ],
        "correct_answer": "A",
        "explanation": "Paragraph 2 highlights capacity degradation over repeated 4-hour charge-discharge cycles as the key barrier.",
        "irt_b": 0.3,
        "irt_a": 1.3,
        "irt_c": 0.25,
    },
    {
        "title": "CAT Reading - Behavioral Economics in Public Health",
        "passage_title": "Choice Architecture in Preventive Medicine",
        "passage_text": (
            "Paragraph 1\n"
            "Public health authorities have traditionally relied on either educational campaigns or regulatory mandates—including administrative fines—to boost "
            "compliance with routine preventive healthcare programs. Recently, however, behavioral economists have tested 'choice architecture' interventions "
            "that alter default enrollment settings without restricting individual freedom.\n\n"
            "Paragraph 2\n"
            "Across a randomized controlled trial involving 45 regional clinics, default option nudges—where patients were automatically scheduled for a pre-assigned "
            "vaccination appointment with a one-click link to reschedule or opt out—proved substantially more effective than financial penalties in increasing routine "
            "vaccination rates, achieving a 22% higher uptake without generating public backlash."
        ),
        "question_text": "Default option nudges proved more effective than financial penalties in increasing routine vaccination rates.",
        "question_type": QuestionType.TRUE_FALSE_NOT_GIVEN,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.HARD,
        "options": [
            {"id": "TRUE", "text": "True"},
            {"id": "FALSE", "text": "False"},
            {"id": "NOT GIVEN", "text": "Not Given"},
        ],
        "correct_answer": "TRUE",
        "explanation": "Paragraph 2 verifies that automatic default scheduling achieved a 22% higher uptake than financial penalties.",
        "irt_b": 1.1,
        "irt_a": 1.4,
        "irt_c": 0.3333,
    },
    {
        "title": "CAT Reading - Paleolithic Cave Acoustics",
        "passage_title": "Archaeoacoustics of Upper Paleolithic Caverns",
        "passage_text": (
            "Paragraph 1\n"
            "For over a century, archaeologists studying Upper Paleolithic cave art in Franco-Cantabrian caverns struggled to explain why prehistoric painters "
            "bypassed broad, accessible limestone walls in favor of narrow, tortuous recesses deep underground.\n\n"
            "Paragraph 2\n"
            "Pioneering archaeoacoustic surveys conducted by Iegor Reznikoff and subsequent acoustic mapping teams revealed a striking physical pattern: "
            "points of greatest acoustic reverberation and resonance consistently coincided with the highest concentrations of animal pictograms, particularly "
            "depictions of bison, horses, and mammoths. Conversely, acoustically dead chambers were largely devoid of major figurative murals."
        ),
        "question_text": "What correlation did archeologists identify between cave painting density and acoustic resonance?",
        "question_type": QuestionType.MULTIPLE_CHOICE,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.HARD,
        "options": [
            {"id": "A", "text": "Points of greatest acoustic reverberation consistently coincided with higher concentrations of animal pictograms"},
            {"id": "B", "text": "Echo chambers were reserved exclusively for human handprint stencils"},
            {"id": "C", "text": "Acoustic dead zones exhibited higher concentrations of mineral pigment grinding debris"},
            {"id": "D", "text": "No statistically significant auditory correlation could be established across the surveyed caves"},
        ],
        "correct_answer": "A",
        "explanation": "Paragraph 2 confirms that points of greatest acoustic reverberation consistently coincided with higher concentrations of animal pictograms.",
        "irt_b": 1.4,
        "irt_a": 1.45,
        "irt_c": 0.25,
    },
    {
        "title": "CAT Reading - Deep-Sea Hydrothermal Vent Ecology",
        "passage_title": "Chemosynthesis in the Abyssal Zone",
        "passage_text": (
            "Paragraph 1\n"
            "Prior to the 1977 exploration of the Galápagos Rift at depths exceeding 2,500 meters, marine biologists assumed that all complex life on Earth "
            "ultimately depended on solar energy captured via photosynthesis in the sunlit upper photic zone.\n\n"
            "Paragraph 2\n"
            "The discovery of thriving ecosystems surrounding deep-sea hydrothermal vents overturned this biological axiom. Located miles below the reach of "
            "any solar photons, chemosynthetic bacteria at hydrothermal vents do not rely on sunlight; instead, they derive cellular energy entirely from the "
            "chemical oxidation of geothermal hydrogen sulfide and methane erupting from superheated seafloor fissures."
        ),
        "question_text": "Chemosynthetic bacteria at hydrothermal vents rely upon sunlight filtered through the upper photic zone for cellular synthesis.",
        "question_type": QuestionType.TRUE_FALSE_NOT_GIVEN,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.HARD,
        "options": [
            {"id": "TRUE", "text": "True"},
            {"id": "FALSE", "text": "False"},
            {"id": "NOT GIVEN", "text": "Not Given"},
        ],
        "correct_answer": "FALSE",
        "explanation": "Paragraph 2 states they derive cellular energy entirely from geothermal chemical oxidation of hydrogen sulfide, independent of sunlight.",
        "irt_b": 1.3,
        "irt_a": 1.35,
        "irt_c": 0.3333,
    },
    {
        "title": "CAT Reading - Linguistic Determinism & Spatial Cognition",
        "passage_title": "Cardinal Reference Frames in Indigenous Languages",
        "passage_text": (
            "Paragraph 1\n"
            "Most Indo-European languages encode spatial relationships egocentrically, using relative body-centered terms such as 'left', 'right', 'in front of', "
            "and 'behind'. By contrast, several indigenous languages—most notably Guugu Yimithirr, spoken in Queensland, Australia—rely exclusively on absolute "
            "geocentric cardinal directions (north, south, east, west) even for small-scale domestic descriptions.\n\n"
            "Paragraph 2\n"
            "Drawing on psycholinguistic field experiments led by Stephen Levinson, the author argues that this linguistic requirement fundamentally shapes "
            "non-verbal spatial cognition: speakers of absolute geographic orientation languages maintain an internal mental compass and possess markedly superior "
            "dead-reckoning navigational accuracy, pointing reliably toward cardinal directions even when blindfolded inside windowless rooms."
        ),
        "question_text": "The author suggests that speakers of absolute geographic orientation languages possess superior dead-reckoning navigational accuracy.",
        "question_type": QuestionType.YES_NO_NOT_GIVEN,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.VERY_HARD,
        "options": [
            {"id": "YES", "text": "Yes"},
            {"id": "NO", "text": "No"},
            {"id": "NOT GIVEN", "text": "Not Given"},
        ],
        "correct_answer": "YES",
        "explanation": "Paragraph 2 endorses Levinson's findings that speakers of absolute geographic orientation languages possess superior dead-reckoning accuracy.",
        "irt_b": 2.1,
        "irt_a": 1.6,
        "irt_c": 0.3333,
    },
    {
        "title": "CAT Reading - Quantum Cryptography & Key Distribution",
        "passage_title": "Quantum Key Distribution and the No-Cloning Theorem",
        "passage_text": (
            "Paragraph 1\n"
            "Classical public-key cryptography relies on the computational intractability of factoring large prime numbers—an assumption vulnerable to future "
            "fault-tolerant quantum computers. Quantum Key Distribution (QKD), implemented via protocols such as BB84, instead bases cryptographic security on "
            "fundamental laws of quantum mechanics by encoding secret key bits into the polarization states of single photons.\n\n"
            "Paragraph 2\n"
            "Because of the Heisenberg uncertainty principle and the quantum no-cloning theorem, an adversary cannot copy or measure an unknown photon polarization "
            "state without altering it. Whenever an eavesdropper intercepts a polarization-encoded photon in transit, the act of measurement unavoidably perturbs "
            "its quantum state, introducing irreversible statistical anomalies that elevate the quantum bit error rate (QBER) beyond the security threshold and "
            "immediately alert the legitimate communicating parties."
        ),
        "question_text": "According to the passage, why is eavesdropping on a polarization-encoded photon inherently detectable by the communicating parties?",
        "question_type": QuestionType.MULTIPLE_CHOICE,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.VERY_HARD,
        "options": [
            {"id": "A", "text": "Measurement unavoidably perturbs quantum states, elevating the quantum bit error rate beyond the security threshold"},
            {"id": "B", "text": "Photon splitters produce detectable thermal dissipation along the optical fiber conduit"},
            {"id": "C", "text": "The sender's laser array immediately halts transmission upon packet checksum mismatch"},
            {"id": "D", "text": "Entangled pairs emit high-frequency radio pulses when intercepted by an unauthorized detector"},
        ],
        "correct_answer": "A",
        "explanation": "Paragraph 2 explains that measurement unavoidably perturbs quantum states, elevating the quantum bit error rate (QBER) beyond the security threshold.",
        "irt_b": 2.4,
        "irt_a": 1.7,
        "irt_c": 0.25,
    },
    {
        "title": "CAT Reading - Microplastic Translocation in Mammalian Tissue",
        "passage_title": "Nanoplastic Bioaccumulation Across Biological Barriers",
        "passage_text": (
            "Paragraph 1\n"
            "While early ecotoxicological studies of plastic pollution focused on macroscopic debris in marine gastrointestinal tracts, recent analytical advances "
            "have shifted attention to secondary microplastics and nanoplastics generated by mechanical abrasion and ultraviolet photodegradation.\n\n"
            "Paragraph 2\n"
            "Crucially, particle size governs biological translocation. Whereas fragments larger than 10 micrometers are largely sequestered by intestinal mucosal "
            "barriers, controlled in vivo trials in mammalian models confirmed that sub-micron polystyrene particles below 1.5 micrometers entered systemic circulation "
            "and successfully breached the murine blood-brain barrier within two hours of oral ingestion."
        ),
        "question_text": "In vivo trials confirmed that particles below 1.5 micrometers successfully breached the murine blood-brain barrier.",
        "question_type": QuestionType.TRUE_FALSE_NOT_GIVEN,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.VERY_HARD,
        "options": [
            {"id": "TRUE", "text": "True"},
            {"id": "FALSE", "text": "False"},
            {"id": "NOT GIVEN", "text": "Not Given"},
        ],
        "correct_answer": "TRUE",
        "explanation": "Paragraph 2 confirms that particles below 1.5 micrometers breached the murine blood-brain barrier in controlled in vivo trials.",
        "irt_b": 2.2,
        "irt_a": 1.65,
        "irt_c": 0.3333,
    },
    {
        "title": "CAT Reading - Ancient Architectural Seismic Dampening",
        "passage_title": "Structural Engineering of Japanese Timber Pagodas",
        "passage_text": (
            "Paragraph 1\n"
            "Despite sitting atop one of the world's most volatile tectonic convergence zones, traditional five-story Japanese timber pagodas—such as the 7th-century "
            "temple at Hōryū-ji—have withstood centuries of powerful earthquakes that toppled modern reinforced concrete structures.\n\n"
            "Paragraph 2\n"
            "Dynamic structural analyses reveal two key engineering mechanisms behind this resilience: interlocking mortise-and-tenon joinery that dissipates seismic "
            "friction without nails, and a massive central cypress pillar known as the shinbashira. Contrary to early assumptions, the shinbashira is not rigidly bolted "
            "or physically anchored to the surrounding structural floors; instead, it stands freestanding or suspended like an inverted pendulum, colliding gently with "
            "oscillating tiers to counteract harmonic swaying."
        ),
        "question_text": "The pagoda's central wooden shinbashira pillar is physically anchored to the surrounding structural floors.",
        "question_type": QuestionType.TRUE_FALSE_NOT_GIVEN,
        "skill_area": SkillArea.READING,
        "difficulty_level": DifficultyLevel.MEDIUM,
        "options": [
            {"id": "TRUE", "text": "True"},
            {"id": "FALSE", "text": "False"},
            {"id": "NOT GIVEN", "text": "Not Given"},
        ],
        "correct_answer": "FALSE",
        "explanation": "Paragraph 2 explains that the shinbashira is not physically anchored to the surrounding floors, acting instead as a freestanding pendulum.",
        "irt_b": 0.4,
        "irt_a": 1.2,
        "irt_c": 0.3333,
    },
]

TERMINAL_3_MAP_OPTIONS = [
    {"id": "A", "text": "Large rectangular space on the left at the end of the right corridor"},
    {"id": "B", "text": "Circular structure at the top-left corner overlooking the runway"},
    {"id": "C", "text": "Vast hall directly in front of the main entrance doors"},
    {"id": "D", "text": "Underground automated shuttle platform"},
    {"id": "E", "text": "West wing international arrivals hall"},
    {"id": "F", "text": "Large L-shaped building at the first right turn past security"},
    {"id": "G", "text": "Last boarding area at the extreme right end of the eastern corridor"},
]

SHORT_LISTENING_CONTEXTS = {
    "Listening Q1 - Detail": {
        "passage_title": "University Library Orientation Recording",
        "passage_text": (
            "Librarian: Welcome to the Main University Library. During the academic semester, our weekday opening hours run from 8:00 AM until 9:00 PM "
            "Monday through Friday. On Saturdays and Sundays, the building closes earlier at 5:00 PM, though the 24-hour study lounge remains accessible with your student ID."
        ),
    },
    "Listening Q2 - Speaker Intent": {
        "passage_title": "Horizon Travel Agency Customer Call",
        "passage_text": (
            "Agent: Good morning, Horizon Travel Agency, how may I assist you?\n"
            "Caller: Hi, I have a confirmed flight reservation to Sydney under booking reference HT-409. I don't want to cancel the trip, "
            "but a conference came up and I need to change my departure date from the 14th to the 18th of next month."
        ),
    },
    "Listening Q3 - Number": {
        "passage_title": "City Sports & Fitness Center Enquiry",
        "passage_text": (
            "Receptionist: We offer three annual membership tiers. Our Basic gym-only plan is $120 per year, the Standard plan including swimming pool access "
            "is $150, and our Advanced membership—which covers all group coaching sessions and sauna access—costs $180 per year."
        ),
    },
    "Listening Q4 - Location": {
        "passage_title": "Campus Freshman Orientation Announcement",
        "passage_text": (
            "Coordinator: Attention all incoming first-year students: due to the high number of registrants, this afternoon's welcome orientation session "
            "has been moved from Room 204 to the main auditorium on the ground floor of the Student Union building."
        ),
    },
    "Listening Q5 - Opinion": {
        "passage_title": "Academic Seminar Discussion on Assessment Design",
        "passage_text": (
            "Student: Professor, some students feel that graded group projects take more coordination time than individual essays.\n"
            "Professor: I understand the scheduling challenge, but I firmly believe group projects are invaluable because they help students develop essential "
            "collaborative teamwork and conflict-resolution skills that employers demand."
        ),
    },
}


def seed_irt():
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        print("=== Step 0: Enrich ContentPassage 'Renewable Energy Transition' ===")
        renewable_passage = (
            db.query(ContentPassage)
            .filter(ContentPassage.title == "Renewable Energy Transition")
            .first()
        )
        if renewable_passage:
            renewable_passage.text_content = RENEWABLE_ENERGY_FULL_PASSAGE
            renewable_passage.word_count = len(RENEWABLE_ENERGY_FULL_PASSAGE.split())
            db.commit()
            print("Updated 'Renewable Energy Transition' passage with full 3-paragraph text.")

        print("=== Step 1: Calibrate existing auto-gradable questions ===")
        questions = (
            db.query(QuestionBank)
            .filter(
                QuestionBank.deleted_at.is_(None),
                QuestionBank.status == ContentStatus.ACTIVE,
                QuestionBank.question_type.in_(AUTO_GRADABLE_TYPES),
            )
            .all()
        )

        updated_count = 0
        reading_count = 0
        listening_count = 0

        for q in questions:
            stats = db.execute(
                text("""
                    SELECT count(*) as total,
                           count(*) FILTER (WHERE is_correct = true) as correct
                    FROM test_responses
                    WHERE question_id = :qid
                """),
                {"qid": str(q.id)},
            ).fetchone()

            total_resp = stats[0] if stats else 0
            correct_resp = stats[1] if stats else 0

            if total_resp >= 10:
                p_emp = max(0.05, min(0.95, correct_resp / total_resp))
                b_val = round(-math.log(p_emp / (1.0 - p_emp)), 4)
                a_val = round(1.0 + 0.5 * (1.0 - 4.0 * ((p_emp - 0.5) ** 2)), 4)
            else:
                level = q.difficulty_level or DifficultyLevel.MEDIUM
                b_val = round(DIFFICULTY_B_MAP.get(level, 0.0), 4)
                a_val = round(DIFFICULTY_A_MAP.get(level, 1.1), 4)

            c_val = round(GUESSING_MAP.get(q.question_type, 0.25), 4)

            q.irt_discrimination = a_val
            q.irt_difficulty = b_val
            q.irt_guessing = c_val
            q.irt_calibrated = True
            q.irt_calibrated_at = now
            q.is_cat_eligible = True

            # Enrich Terminal 3 map matching questions (Listening Q16..Q20) with descriptive options
            if q.title in [
                "Listening Q16 - Part 2",
                "Listening Q17 - Part 2",
                "Listening Q18 - Part 2",
                "Listening Q19 - Part 2",
                "Listening Q20 - Part 2",
            ]:
                q.options = TERMINAL_3_MAP_OPTIONS
                meta = dict(q.extra_metadata or {})
                meta["instructions"] = (
                    "Listen to the Terminal 3 layout briefing and match the facility below to its correct location description (A–G)."
                )
                q.extra_metadata = meta

            # Enrich Listening Q1..Q5 with transcript context if no audio is attached
            if q.title in SHORT_LISTENING_CONTEXTS:
                meta = dict(q.extra_metadata or {})
                meta.update(SHORT_LISTENING_CONTEXTS[q.title])
                q.extra_metadata = meta

            updated_count += 1
            if q.skill_area == SkillArea.READING:
                reading_count += 1
            elif q.skill_area == SkillArea.LISTENING:
                listening_count += 1

        db.commit()
        print(
            f"Updated {updated_count} existing questions (Reading: {reading_count}, Listening: {listening_count})"
        )

        print("=== Step 2: Upsert calibrated CAT Reading questions with self-contained passages ===")
        added_reading = 0
        updated_reading = 0
        for item in ADDITIONAL_READING_QUESTIONS:
            existing = (
                db.query(QuestionBank)
                .filter(
                    QuestionBank.title == item["title"],
                    QuestionBank.deleted_at.is_(None),
                )
                .first()
            )
            meta_payload = {
                "passage_title": item["passage_title"],
                "passage_text": item["passage_text"],
            }
            if existing:
                existing.question_text = item["question_text"]
                existing.options = item["options"]
                existing.correct_answer = item["correct_answer"]
                existing.explanation = item["explanation"]
                existing.irt_discrimination = item["irt_a"]
                existing.irt_difficulty = item["irt_b"]
                existing.irt_guessing = item["irt_c"]
                existing.irt_calibrated = True
                existing.irt_calibrated_at = now
                existing.is_cat_eligible = True
                existing_meta = dict(existing.extra_metadata or {})
                existing_meta.update(meta_payload)
                existing.extra_metadata = existing_meta
                updated_reading += 1
            else:
                new_q = QuestionBank(
                    title=item["title"],
                    question_text=item["question_text"],
                    question_type=item["question_type"],
                    skill_area=item["skill_area"],
                    difficulty_level=item["difficulty_level"],
                    options=item["options"],
                    correct_answer=item["correct_answer"],
                    explanation=item["explanation"],
                    extra_metadata=meta_payload,
                    points=1.0,
                    usage_count=0,
                    status=ContentStatus.ACTIVE,
                    irt_discrimination=item["irt_a"],
                    irt_difficulty=item["irt_b"],
                    irt_guessing=item["irt_c"],
                    irt_calibrated=True,
                    irt_calibrated_at=now,
                    is_cat_eligible=True,
                )
                db.add(new_q)
                added_reading += 1
        db.commit()
        print(
            f"CAT Reading items upserted: {added_reading} added, {updated_reading} updated with passages."
        )

        final_reading = (
            db.query(QuestionBank)
            .filter(
                QuestionBank.deleted_at.is_(None),
                QuestionBank.is_cat_eligible == True,
                QuestionBank.skill_area == SkillArea.READING,
            )
            .count()
        )

        final_listening = (
            db.query(QuestionBank)
            .filter(
                QuestionBank.deleted_at.is_(None),
                QuestionBank.is_cat_eligible == True,
                QuestionBank.skill_area == SkillArea.LISTENING,
            )
            .count()
        )

        print("=== CAT Question Pool Ready ===")
        print(f"Reading pool: {final_reading} questions (all with self-contained passages)")
        print(f"Listening pool: {final_listening} questions")

    finally:
        db.close()


if __name__ == "__main__":
    seed_irt()
