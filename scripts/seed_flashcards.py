import asyncio
import os
import sys

# Thêm đường dẫn project vào sys.path để có thể import từ app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.flashcard import FlashcardDeck, Flashcard, TopicTag, DeckLevel, WordType

OXFORD_WORDS = [
    {"word": "abstract", "ipa": "/ˈæb.strækt/", "word_type": WordType.ADJECTIVE, "definition_en": "Existing in thought or as an idea but not having a physical or concrete existence.", "definition_vi": "Trừu tượng", "example_sentence": "Abstract concepts such as love or beauty."},
    {"word": "accurate", "ipa": "/ˈæk.jə.rət/", "word_type": WordType.ADJECTIVE, "definition_en": "Correct in all details; exact.", "definition_vi": "Chính xác", "example_sentence": "Accurate information about the illness is essential."},
    {"word": "acknowledge", "ipa": "/əkˈnɒl.ɪdʒ/", "word_type": WordType.VERB, "definition_en": "Accept or admit the existence or truth of.", "definition_vi": "Công nhận", "example_sentence": "The government acknowledged that the tax was unfair."},
    {"word": "aggregate", "ipa": "/ˈæɡ.rɪ.ɡət/", "word_type": WordType.NOUN, "definition_en": "A whole formed by combining several separate elements.", "definition_vi": "Tổng số, tập hợp", "example_sentence": "The council was an aggregate of three regional assemblies."},
    {"word": "allocate", "ipa": "/ˈæl.ə.keɪt/", "word_type": WordType.VERB, "definition_en": "Distribute (resources or duties) for a particular purpose.", "definition_vi": "Phân bổ", "example_sentence": "The authorities allocated 50,000 places to refugees."},
    {"word": "attach", "ipa": "/əˈtætʃ/", "word_type": WordType.VERB, "definition_en": "Fasten or join one thing to another.", "definition_vi": "Đính kèm", "example_sentence": "He made certain that the trailer was securely attached to the van."},
    {"word": "bond", "ipa": "/bɒnd/", "word_type": WordType.NOUN, "definition_en": "A relationship between people or groups based on shared feelings, interests, or experiences.", "definition_vi": "Sự liên kết", "example_sentence": "There was a close bond between them."},
    {"word": "brief", "ipa": "/briːf/", "word_type": WordType.ADJECTIVE, "definition_en": "Of short duration.", "definition_vi": "Ngắn gọn", "example_sentence": "The president made a brief visit to Beijing."},
    {"word": "capable", "ipa": "/ˈkeɪ.pə.bəl/", "word_type": WordType.ADJECTIVE, "definition_en": "Having the ability, fitness, or quality necessary to do or achieve a specified thing.", "definition_vi": "Có khả năng", "example_sentence": "I'm quite capable of taking care of myself."},
    {"word": "cite", "ipa": "/saɪt/", "word_type": WordType.VERB, "definition_en": "Quote (a passage, book, or author) as evidence for or justification of an argument or statement.", "definition_vi": "Trích dẫn", "example_sentence": "Authors who are highly regarded by their peers tend to be cited."},
    {"word": "cooperate", "ipa": "/kəʊˈɒp.ər.eɪt/", "word_type": WordType.VERB, "definition_en": "Work jointly towards the same end.", "definition_vi": "Hợp tác", "example_sentence": "The leaders promised to cooperate in ending the civil war."},
    {"word": "discrimination", "ipa": "/dɪˌskrɪm.ɪˈneɪ.ʃən/", "word_type": WordType.NOUN, "definition_en": "The unjust or prejudicial treatment of different categories of people or things.", "definition_vi": "Sự phân biệt đối xử", "example_sentence": "Victims of racial discrimination."},
    {"word": "display", "ipa": "/dɪˈspleɪ/", "word_type": WordType.VERB, "definition_en": "Make a prominent exhibition of (something) in a place where it can be easily seen.", "definition_vi": "Hiển thị, trưng bày", "example_sentence": "The palace used to display a series of portraits."},
    {"word": "diversity", "ipa": "/daɪˈvɜː.sə.ti/", "word_type": WordType.NOUN, "definition_en": "The state of being diverse; variety.", "definition_vi": "Sự đa dạng", "example_sentence": "There was considerable diversity in the style of the reports."},
    {"word": "domain", "ipa": "/dəˈmeɪn/", "word_type": WordType.NOUN, "definition_en": "An area of territory owned or controlled by a ruler or government.", "definition_vi": "Lĩnh vực, vùng", "example_sentence": "The southwestern French domains of the Plantagenets."},
    {"word": "edition", "ipa": "/ɪˈdɪʃ.ən/", "word_type": WordType.NOUN, "definition_en": "A particular form or version of a published text.", "definition_vi": "Phiên bản", "example_sentence": "A paperback edition."},
    {"word": "enhance", "ipa": "/ɪnˈhɑːns/", "word_type": WordType.VERB, "definition_en": "Intensify, increase, or further improve the quality, value, or extent of.", "definition_vi": "Nâng cao", "example_sentence": "His refusal does nothing to enhance his reputation."},
    {"word": "estate", "ipa": "/ɪˈsteɪt/", "word_type": WordType.NOUN, "definition_en": "An area or amount of land or property, in particular.", "definition_vi": "Điền trang, bất động sản", "example_sentence": "His family owned a large estate in the Scottish borders."},
    {"word": "exceed", "ipa": "/ɪkˈsiːd/", "word_type": WordType.VERB, "definition_en": "Be greater in number or size than (a quantity, number, or other measurable thing).", "definition_vi": "Vượt quá", "example_sentence": "Production costs have exceeded £60,000."},
    {"word": "expert", "ipa": "/ˈek.spɜːt/", "word_type": WordType.NOUN, "definition_en": "A person who has a comprehensive and authoritative knowledge of or skill in a particular area.", "definition_vi": "Chuyên gia", "example_sentence": "Experts in child psychology."},
    {"word": "explicit", "ipa": "/ɪkˈsplɪs.ɪt/", "word_type": WordType.ADJECTIVE, "definition_en": "Stated clearly and in detail, leaving no room for confusion or doubt.", "definition_vi": "Rõ ràng", "example_sentence": "The speaker's intentions were not made explicit."},
    {"word": "federal", "ipa": "/ˈfed.ər.əl/", "word_type": WordType.ADJECTIVE, "definition_en": "Having or relating to a system of government in which several states form a unity but remain independent in internal affairs.", "definition_vi": "Liên bang", "example_sentence": "Russia's federation treaty sharing powers among Russia's federal and local governments."},
    {"word": "fee", "ipa": "/fiː/", "word_type": WordType.NOUN, "definition_en": "A payment made to a professional person or to a professional or public body in exchange for advice or services.", "definition_vi": "Phí", "example_sentence": "They were charged a fee for the service."},
    {"word": "flexibility", "ipa": "/ˌflek.səˈbɪl.ə.ti/", "word_type": WordType.NOUN, "definition_en": "The quality of bending easily without breaking.", "definition_vi": "Sự linh hoạt", "example_sentence": "Players gained improved flexibility in their ankles."},
    {"word": "furthermore", "ipa": "/ˌfɜː.ðəˈmɔːr/", "word_type": WordType.ADVERB, "definition_en": "In addition; besides (used to introduce a fresh consideration in an argument).", "definition_vi": "Hơn nữa", "example_sentence": "It was also a highly desirable political end. Furthermore, it gave the English a door into France."},
    {"word": "gender", "ipa": "/ˈdʒen.dər/", "word_type": WordType.NOUN, "definition_en": "Either of the two sexes (male and female).", "definition_vi": "Giới tính", "example_sentence": "Traditional concepts of gender."},
    {"word": "ignore", "ipa": "/ɪɡˈnɔːr/", "word_type": WordType.VERB, "definition_en": "Refuse to take notice of or acknowledge; disregard intentionally.", "definition_vi": "Phớt lờ", "example_sentence": "He ignored her outraged question."},
    {"word": "incentive", "ipa": "/ɪnˈsen.tɪv/", "word_type": WordType.NOUN, "definition_en": "A thing that motivates or encourages one to do something.", "definition_vi": "Sự khuyến khích", "example_sentence": "There is no incentive for customers to conserve water."},
    {"word": "incidence", "ipa": "/ˈɪn.sɪ.dəns/", "word_type": WordType.NOUN, "definition_en": "The occurrence, rate, or frequency of a disease, crime, or something else undesirable.", "definition_vi": "Tỷ lệ mắc phải", "example_sentence": "An increased incidence of cancer."},
    {"word": "incorporate", "ipa": "/ɪnˈkɔː.pər.eɪt/", "word_type": WordType.VERB, "definition_en": "Take in or contain (something) as part of a whole; include.", "definition_vi": "Kết hợp", "example_sentence": "He has incorporated in his proposals a large number of measures."},
    {"word": "index", "ipa": "/ˈɪn.deks/", "word_type": WordType.NOUN, "definition_en": "An alphabetical list of records or pointers to data.", "definition_vi": "Chỉ số, danh mục", "example_sentence": "Clear cross-references and a good index."},
    {"word": "inhibit", "ipa": "/ɪnˈhɪb.ɪt/", "word_type": WordType.VERB, "definition_en": "Hinder, restrain, or prevent (an action or process).", "definition_vi": "Ngăn chặn", "example_sentence": "Cold inhibits plant growth."},
    {"word": "initiative", "ipa": "/ɪˈnɪʃ.ə.tɪv/", "word_type": WordType.NOUN, "definition_en": "The ability to assess and initiate things independently.", "definition_vi": "Sáng kiến", "example_sentence": "Use your initiative, imagination, and common sense."},
    {"word": "input", "ipa": "/ˈɪn.pʊt/", "word_type": WordType.NOUN, "definition_en": "What is put in, taken in, or operated on by any process or system.", "definition_vi": "Đầu vào", "example_sentence": "The input of data into the computer."},
    {"word": "instruct", "ipa": "/ɪnˈstrʌkt/", "word_type": WordType.VERB, "definition_en": "Direct or command someone to do something.", "definition_vi": "Hướng dẫn", "example_sentence": "She instructed him to wait."},
    {"word": "intelligence", "ipa": "/ɪnˈtel.ɪ.dʒəns/", "word_type": WordType.NOUN, "definition_en": "The ability to acquire and apply knowledge and skills.", "definition_vi": "Sự thông minh", "example_sentence": "An eminent man of great intelligence."},
    {"word": "interval", "ipa": "/ˈɪn.tə.vəl/", "word_type": WordType.NOUN, "definition_en": "An intervening time or space.", "definition_vi": "Khoảng thời gian", "example_sentence": "After his departure, there was an interval of many years without any meetings."},
    {"word": "lecture", "ipa": "/ˈlek.tʃər/", "word_type": WordType.NOUN, "definition_en": "An educational talk to an audience, especially to students in a university or college.", "definition_vi": "Bài giảng", "example_sentence": "In each course there are supporting lectures and tutorials."},
    {"word": "migrate", "ipa": "/maɪˈɡreɪt/", "word_type": WordType.VERB, "definition_en": "Move from one region or habitat to another.", "definition_vi": "Di cư", "example_sentence": "As autumn arrives, the birds migrate south."},
    {"word": "minimum", "ipa": "/ˈmɪn.ɪ.məm/", "word_type": WordType.NOUN, "definition_en": "The least or smallest amount or quantity possible, attainable, or required.", "definition_vi": "Mức tối thiểu", "example_sentence": "They checked the minimum temperature."},
    {"word": "ministry", "ipa": "/ˈmɪn.ɪ.stri/", "word_type": WordType.NOUN, "definition_en": "A government department headed by a minister of state.", "definition_vi": "Bộ", "example_sentence": "The Ministry of Agriculture."},
    {"word": "motive", "ipa": "/ˈməʊ.tɪv/", "word_type": WordType.NOUN, "definition_en": "A reason for doing something.", "definition_vi": "Động cơ", "example_sentence": "Police were unable to establish a motive for his murder."},
    {"word": "neutral", "ipa": "/ˈnjuː.trəl/", "word_type": WordType.ADJECTIVE, "definition_en": "Not supporting or helping either side in a conflict, disagreement, etc.; impartial.", "definition_vi": "Trung lập", "example_sentence": "During the Second World War, Portugal was neutral."},
    {"word": "nevertheless", "ipa": "/ˌnev.ə.ðəˈles/", "word_type": WordType.ADVERB, "definition_en": "In spite of that; notwithstanding; all the same.", "definition_vi": "Tuy nhiên", "example_sentence": "Statements which, although literally true, are nevertheless misleading."},
    {"word": "overseas", "ipa": "/ˌəʊ.vəˈsiːz/", "word_type": WordType.ADVERB, "definition_en": "In or to a foreign country, especially one across the sea.", "definition_vi": "Nước ngoài", "example_sentence": "He spent quite a lot of time working overseas."},
    {"word": "precede", "ipa": "/prɪˈsiːd/", "word_type": WordType.VERB, "definition_en": "Come before (something) in time.", "definition_vi": "Đứng trước", "example_sentence": "A gun battle had preceded the explosions."},
    {"word": "presume", "ipa": "/prɪˈzjuːm/", "word_type": WordType.VERB, "definition_en": "Suppose that something is the case on the basis of probability.", "definition_vi": "Giả định", "example_sentence": "I presumed that the man had been escorted from the building."},
    {"word": "rational", "ipa": "/ˈræʃ.ən.əl/", "word_type": WordType.ADJECTIVE, "definition_en": "Based on or in accordance with reason or logic.", "definition_vi": "Có lý trí", "example_sentence": "I'm sure there's a perfectly rational explanation."},
    {"word": "recover", "ipa": "/rɪˈkʌv.ər/", "word_type": WordType.VERB, "definition_en": "Return to a normal state of health, mind, or strength.", "definition_vi": "Hồi phục", "example_sentence": "Neil is still recovering from shock."},
    {"word": "reveal", "ipa": "/rɪˈviːl/", "word_type": WordType.VERB, "definition_en": "Make (previously unknown or secret information) known to others.", "definition_vi": "Tiết lộ", "example_sentence": "Brenda was forced to reveal Robbie's whereabouts."},
]

def seed_data():
    print("Bắt đầu seed dữ liệu flashcard...")
    with SessionLocal() as db:
        # Create deck
        deck = FlashcardDeck(
            title="Oxford Academic List (Demo)",
            description="50 từ vựng học thuật quan trọng từ Oxford Word List.",
            topic_tag=TopicTag.ACADEMIC,
            level=DeckLevel.ADVANCED,
            is_public=True,
            card_count=len(OXFORD_WORDS)
        )
        db.add(deck)
        db.commit()
        db.refresh(deck)
        print(f"Đã tạo deck: {deck.title} (ID: {deck.id})")

        # Create flashcards
        for item in OXFORD_WORDS:
            card = Flashcard(
                deck_id=deck.id,
                word=item["word"],
                ipa=item["ipa"],
                word_type=item["word_type"],
                definition_en=item["definition_en"],
                definition_vi=item["definition_vi"],
                example_sentence=item["example_sentence"]
            )
            db.add(card)
        db.commit()
        print(f"Đã tạo {len(OXFORD_WORDS)} flashcard thành công!")

if __name__ == "__main__":
    seed_data()
