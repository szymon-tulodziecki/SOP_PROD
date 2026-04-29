from dataclasses import dataclass


@dataclass(frozen=True)
class LogbookEntryDTO:
    id: object
    entry_date: object
    hours_count: int
    description: str
    learning_outcomes: list

    @classmethod
    def from_model(cls, entry):
        return cls(
            id=entry.id,
            entry_date=entry.entry_date,
            hours_count=entry.duration_hours,
            description=entry.description,
            learning_outcomes=list(getattr(entry, 'efekty_uczenia', None) or []),
        )
