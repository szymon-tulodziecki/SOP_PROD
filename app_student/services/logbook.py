from dataclasses import dataclass


@dataclass(frozen=True)
class LogbookEntryDTO:
    id: object
    entry_date: object
    hours_count: int
    description: str
    learning_outcomes: list
    supervisor_comment: str | None

    @classmethod
    def from_model(cls, entry):
        return cls(
            id=entry.id,
            entry_date=entry.entry_date,
            hours_count=entry.duration_hours,
            description=entry.description,
            learning_outcomes=list(entry.learning_outcomes),
            supervisor_comment=entry.supervisor_comment,
        )
