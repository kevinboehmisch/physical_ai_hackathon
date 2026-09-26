"""Question pool for the target role, selected deterministically per session."""

import random
from typing import Literal
from dataclasses import dataclass


QuestionKind = Literal["intro", "behavioral", "technical"]

# Interview shape: one introduction, two behavioural, two light technical questions.
QUESTION_PLAN: tuple[QuestionKind, ...] = ("intro", "behavioral", "behavioral", "technical", "technical")

ROLE_TITLE = {
    "de": "Software Engineering Intern (Master), Google, Sommer 2027",
    "en": "Software Engineering Intern (MS), Google, Summer 2027",
}

ROLE_SUMMARY = {
    "de": (
        "Praktikum für Master-Studierende der Informatik. Erwartet werden Programmiererfahrung in mindestens zwei "
        "Allzwecksprachen (z. B. C++, Java, Python, JavaScript), solide Grundlagen in Datenstrukturen und Algorithmen "
        "sowie die Fähigkeit, Probleme zu analysieren und Lösungen abzuwägen. Von Vorteil: Erfahrung mit verteilten "
        "Systemen, Linux, Webentwicklung oder KI/ML. Im Team werden Skripte zur Automatisierung geschrieben, "
        "Ergebnisse bewertet und Lösungen gemeinsam mit Kolleginnen, Kollegen und Managern umgesetzt."
    ),
    "en": (
        "Internship for master's students in computer science. Expected: coding experience in at least two general "
        "purpose languages (e.g. C++, Java, Python, JavaScript), solid data structures and algorithms, and the "
        "ability to analyse problems and weigh solutions. Nice to have: distributed systems, Linux, web development "
        "or AI/ML. Interns write automation scripts, evaluate results and ship solutions together with peers and "
        "managers."
    ),
}


@dataclass(frozen=True)
class InterviewQuestion:
    """One interview question with guidance for the interviewer and for the content analysis."""

    kind: QuestionKind
    text: str
    interviewer_hint: str
    evaluation_hint: str


_QUESTIONS_DE: dict[QuestionKind, tuple[InterviewQuestion, ...]] = {
    "intro": (
        InterviewQuestion(
            kind="intro",
            text="Stell dich bitte kurz vor: Was studierst du, und was hat dich zur Softwareentwicklung gebracht?",
            interviewer_hint="Kurz halten lassen (1 bis 2 Minuten). Bei reiner Aufzählung nach einem Projekt fragen, "
            "auf das die Person stolz ist.",
            evaluation_hint="Roter Faden, Bezug zur Rolle, ein konkretes Projekt oder Interesse statt Aufzählung.",
        ),
    ),
    "behavioral": (
        InterviewQuestion(
            kind="behavioral",
            text="Erzähl mir von einem Konflikt in einem Team, in dem du mitgearbeitet hast. Wie bist du damit "
            "umgegangen, und was kam dabei heraus?",
            interviewer_hint="STAR: Situation, Aufgabe, eigenes Handeln, Ergebnis. Wenn das eigene Handeln oder das "
            "Ergebnis fehlt, genau danach fragen.",
            evaluation_hint="STAR vollständig, eigener Anteil klar benannt, Ergebnis und Lernerfahrung konkret.",
        ),
        InterviewQuestion(
            kind="behavioral",
            text="Beschreib eine Situation, in der ein Projekt oder eine Abgabe nicht wie geplant lief. Was hast du "
            "konkret getan?",
            interviewer_hint="STAR. Bei allgemeinen Aussagen nach dem konkreten Zeitpunkt, den Beteiligten und der "
            "eigenen Entscheidung fragen.",
            evaluation_hint="Ehrliche Fehleranalyse, eigene Entscheidung, Ergebnis, was beim nächsten Mal anders wäre.",
        ),
        InterviewQuestion(
            kind="behavioral",
            text="Erzähl von einem Moment, in dem du dir etwas Technisches schnell selbst beibringen musstest. Wie "
            "bist du vorgegangen?",
            interviewer_hint="STAR. Nachfragen, wie die Person Lernquellen ausgewählt und den Fortschritt geprüft hat.",
            evaluation_hint="Konkretes Thema, strukturierter Lernweg, messbares Ergebnis.",
        ),
        InterviewQuestion(
            kind="behavioral",
            text="Wann hast du zuletzt Feedback zu deinem Code bekommen, das dir nicht gefallen hat? Wie hast du "
            "reagiert?",
            interviewer_hint="STAR. Nachfragen, was die Person konkret geändert hat.",
            evaluation_hint="Umgang mit Kritik, konkrete Anpassung, Reflexion statt Rechtfertigung.",
        ),
    ),
    "technical": (
        InterviewQuestion(
            kind="technical",
            text="Erklär mir den Unterschied zwischen einer Liste und einer Hashmap. Wann würdest du welche nehmen?",
            interviewer_hint="Leichte Frage. Bei Unsicherheit nach der Laufzeit für Suchen und Einfügen fragen.",
            evaluation_hint="Zugriff O(1) vs. O(n), Reihenfolge, Speicher, Kollisionen, passende Beispiele.",
        ),
        InterviewQuestion(
            kind="technical",
            text="Wie würdest du herausfinden, warum ein Skript, das nachts automatisch läuft, gelegentlich abbricht?",
            interviewer_hint="Leichte Frage zu Debugging und Automatisierung. Nach Logging, Reproduktion und "
            "Monitoring fragen, wenn nur geraten wird.",
            evaluation_hint="Logs, Reproduzierbarkeit, Fehlerbehandlung, Retry, Monitoring, Hypothesen prüfen.",
        ),
        InterviewQuestion(
            kind="technical",
            text="Was ist Rekursion, und wann ist eine Schleife die bessere Wahl?",
            interviewer_hint="Leichte Frage. Bei Bedarf nach Stack-Tiefe oder einem Beispiel fragen.",
            evaluation_hint="Basisfall, Aufrufstapel, Lesbarkeit vs. Stack-Overflow-Risiko, Beispiel.",
        ),
        InterviewQuestion(
            kind="technical",
            text="Du hast zwei Programmiersprachen, mit denen du dich wohlfühlst. Was gefällt dir an der einen, was "
            "nervt dich an der anderen?",
            interviewer_hint="Leichte Frage zu Sprachkenntnis und Reflexion. Nach einem konkreten Beispiel fragen.",
            evaluation_hint="Konkrete Spracheigenschaften (Typsystem, Tooling, Speicher), keine Floskeln.",
        ),
        InterviewQuestion(
            kind="technical",
            text="Was bedeutet es, wenn ein System verteilt ist, und welches Problem taucht dabei auf, das es auf "
            "einem einzelnen Rechner nicht gibt?",
            interviewer_hint="Leichte Einstiegsfrage zu verteilten Systemen. Ein Problem reicht (Netzwerkausfall, "
            "Konsistenz, Latenz).",
            evaluation_hint="Mehrere Rechner, Netzwerk als Fehlerquelle, Konsistenz oder Partial Failure genannt.",
        ),
    ),
}

_QUESTIONS_EN: dict[QuestionKind, tuple[InterviewQuestion, ...]] = {
    "intro": (
        InterviewQuestion(
            kind="intro",
            text="Please introduce yourself briefly: what are you studying, and what drew you to software engineering?",
            interviewer_hint="Keep it to one or two minutes. If it is only a list, ask about one project they are proud of.",
            evaluation_hint="Clear thread, relevance to the role, one concrete project or interest instead of a list.",
        ),
    ),
    "behavioral": (
        InterviewQuestion(
            kind="behavioral",
            text="Tell me about a conflict in a team you worked in. How did you handle it, and what was the outcome?",
            interviewer_hint="STAR: situation, task, own action, result. Probe for the missing part.",
            evaluation_hint="Complete STAR, own contribution named, concrete result and learning.",
        ),
        InterviewQuestion(
            kind="behavioral",
            text="Describe a time a project or deadline did not go as planned. What exactly did you do?",
            interviewer_hint="STAR. Ask for the specific moment, people involved and the decision they made.",
            evaluation_hint="Honest analysis, own decision, result, what they would do differently.",
        ),
        InterviewQuestion(
            kind="behavioral",
            text="Tell me about a time you had to teach yourself something technical quickly. How did you go about it?",
            interviewer_hint="STAR. Ask how they picked resources and checked progress.",
            evaluation_hint="Concrete topic, structured approach, measurable result.",
        ),
    ),
    "technical": (
        InterviewQuestion(
            kind="technical",
            text="Explain the difference between a list and a hash map. When would you pick which?",
            interviewer_hint="Easy question. If unsure, ask about lookup and insert complexity.",
            evaluation_hint="O(1) vs O(n) access, ordering, memory, collisions, fitting examples.",
        ),
        InterviewQuestion(
            kind="technical",
            text="How would you find out why a script that runs automatically every night occasionally fails?",
            interviewer_hint="Easy debugging question. Probe for logging, reproduction and monitoring.",
            evaluation_hint="Logs, reproducibility, error handling, retries, monitoring, testing hypotheses.",
        ),
        InterviewQuestion(
            kind="technical",
            text="What is recursion, and when is a loop the better choice?",
            interviewer_hint="Easy question. Ask about stack depth or an example if needed.",
            evaluation_hint="Base case, call stack, readability vs stack overflow risk, example.",
        ),
    ),
}

_QUESTION_POOLS = {"de": _QUESTIONS_DE, "en": _QUESTIONS_EN}


def build_question_set(language: str, seed: int | None = None) -> list[InterviewQuestion]:
    """Pick one question per slot of QUESTION_PLAN without repeating a question."""
    pool = _QUESTION_POOLS[language]
    rng = random.Random(seed)
    remaining = {kind: list(questions) for kind, questions in pool.items()}
    selected: list[InterviewQuestion] = []
    for kind in QUESTION_PLAN:
        candidates = remaining[kind]
        if not candidates:
            raise ValueError(f"Question pool for {kind!r} exhausted in language {language!r}")
        question = rng.choice(candidates)
        candidates.remove(question)
        selected.append(question)
    return selected
