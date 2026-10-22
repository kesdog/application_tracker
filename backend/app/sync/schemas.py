"""Version 1 strict compact projections, shared by journal and importer."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

import json
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


class WireModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ApplicationState(WireModel):
    company: str = Field(min_length=1, max_length=300)
    job_title: str = Field(min_length=1, max_length=300)
    date_applied: date
    job_url: str | None = Field(default=None, max_length=2048)
    email_reference: str | None = Field(default=None, max_length=2048)
    status: Literal['SUBMITTED', 'INTERVIEW', 'CLOSED']
    outcome: Literal['SUCCESSFUL', 'UNSUCCESSFUL', 'WITHDRAWN', 'JOB_CANCELLED', 'GHOSTED'] | None = None
    deleted: bool = False

    @model_validator(mode='after')
    def consistent(self):
        if not self.company.strip() or not self.job_title.strip() or not ((self.job_url or '').strip() or (self.email_reference or '').strip()):
            raise ValueError('Application summary and source are required')
        if self.outcome and self.status != 'CLOSED':
            raise ValueError('An outcome requires CLOSED')
        return self


class TaskState(WireModel):
    application_id: UUID
    title: str = Field(min_length=1, max_length=300)
    status: Literal['PENDING', 'COMPLETED', 'CANCELLED']
    due_at: datetime | None = None
    completed_at: datetime | None = None
    deleted: bool = False

    @model_validator(mode='after')
    def consistent(self):
        if not self.title.strip() or (self.status == 'COMPLETED') != (self.completed_at is not None):
            raise ValueError('Task completion state is inconsistent')
        return self


class InterviewState(WireModel):
    application_id: UUID
    scheduled_at: datetime
    type: Literal['PHONE', 'HR', 'TECHNICAL', 'ONSITE', 'FINAL', 'OTHER']
    duration: int | None = Field(default=None, gt=0)
    deleted: bool = False


class FollowUpState(WireModel):
    application_id: UUID
    sequence_number: int = Field(gt=0)
    due_at: datetime
    status: Literal['PREPARED', 'READY', 'SENT']
    sent_at: datetime | None = None
    archived_at: datetime | None = None
    snoozed_until: datetime | None = None
    is_automatic: bool = False
    parent_followup_id: UUID | None = None
    deleted: bool = False

    @model_validator(mode='after')
    def consistent(self):
        if (self.status == 'SENT') != (self.sent_at is not None):
            raise ValueError('Sent state requires an actual send timestamp')
        return self


STATES = {'application': ApplicationState, 'task': TaskState, 'interview': InterviewState, 'followup': FollowUpState}
FIELD_ADAPTERS = {entity: {name: TypeAdapter(field.rebuild_annotation()) for name, field in model.model_fields.items()}
                  for entity, model in STATES.items()}


class Mutation(WireModel):
    version: Literal[1] = 1
    event_id: UUID
    workspace_id: UUID
    device_id: UUID
    device_seq: int = Field(gt=0)
    entity: Literal['application', 'task', 'interview', 'followup']
    entity_id: UUID
    op: Literal['create', 'patch', 'delete', 'resolution']
    parents: list[UUID] = Field(default_factory=list, max_length=1000)
    changes: dict = Field(min_length=1)
    actor: Literal['HUMAN', 'AGENT', 'SYSTEM'] = 'SYSTEM'

    @model_validator(mode='after')
    def allowlist(self):
        fields = STATES[self.entity].model_fields
        if self.changes.keys() - fields.keys():
            raise ValueError('Fields outside Compact Sync are forbidden')
        adapters = FIELD_ADAPTERS[self.entity]
        self.changes = {name: json.loads(adapters[name].dump_json(adapters[name].validate_python(value)))
                        for name, value in self.changes.items()}
        if self.event_id in self.parents or len(set(self.parents)) != len(self.parents):
            raise ValueError('Invalid causal parents')
        if self.op == 'create' and self.parents:
            raise ValueError('Creates have no parents')
        if self.op != 'create' and not self.parents:
            raise ValueError('Updates require causal parents')
        if self.op in {'create', 'resolution'}:
            STATES[self.entity].model_validate(self.changes)
        if self.op == 'delete' and self.changes != {'deleted': True}:
            raise ValueError('Deletes carry only their tombstone')
        return self


class Batch(WireModel):
    version: Literal[1] = 1
    workspace_id: UUID
    batch_id: UUID
    device_id: UUID
    kind: Literal['events', 'checkpoint', 'ack'] = 'events'
    mutations: list[Mutation] = Field(default_factory=list, max_length=1000000)
    acknowledgments: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode='after')
    def workspace(self):
        if any(item.workspace_id != self.workspace_id for item in self.mutations):
            raise ValueError('Mixed workspaces')
        if self.kind == 'events' and any(item.device_id != self.device_id for item in self.mutations):
            raise ValueError('Mutation batch does not belong to its originating device')
        for device, sequence in self.acknowledgments.items():
            UUID(device)
            if type(sequence) is not int or sequence < 0:
                raise ValueError('Invalid acknowledgment')
        if self.kind == 'ack' and self.mutations:
            raise ValueError('Acknowledgments cannot contain edits')
        return self
