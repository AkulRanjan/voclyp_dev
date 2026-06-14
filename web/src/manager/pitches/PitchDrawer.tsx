import { useState } from "react";
import { Drawer } from "../../components/Drawer";
import { Chip } from "../../components/Chip";
import { AudioPlayer } from "../../components/AudioPlayer";
import { scoreBand, intentTone } from "../../lib/bands";
import { secondsToClock, formatTimestamp } from "../../lib/format";
import { SIGNAL_GROUPS, COACHING_GROUPS } from "../../lib/chips";
import { Badge } from "../../components/Badge";
import type { PitchInstance, PitchRow } from "../../data/types";

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="dsec">
      <div className="dsec__label">{label}</div>
      {children}
    </section>
  );
}

function ScoreCell({ label, value }: { label: string; value: number }) {
  return (
    <div className="dscore">
      <span className="dscore__label">{label}</span>
      <span className="dscore__value">{value}/10</span>
    </div>
  );
}

function SummaryField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="dfield">
      <span className="dfield__k">{label}</span>
      <span className="dfield__v">{value}</span>
    </div>
  );
}

export function PitchDrawer({ row, onClose }: { row: PitchRow | null; onClose: () => void }) {
  // Which instance is shown (rows can hold more than one recording).
  const [activeIdx, setActiveIdx] = useState(0);
  const instance: PitchInstance | undefined = row?.instances[activeIdx] ?? row?.instances[0];

  // Reset to the first instance whenever a different row opens.
  const rowId = row?.id;
  const [seenRow, setSeenRow] = useState<string | undefined>(rowId);
  if (rowId !== seenRow) {
    setSeenRow(rowId);
    setActiveIdx(0);
  }

  if (!row || !instance) return null;

  const band = scoreBand(instance.score);

  return (
    <Drawer
      open
      onClose={onClose}
      title={
        <span>
          {row.brand} <span className="dtitle__sep">·</span> Instance #{instance.index}
        </span>
      }
    >
      {row.instances.length > 1 && (
        <div className="dinstances">
          {row.instances.map((ins, i) => (
            <button
              key={ins.index}
              className={`dinstance${i === activeIdx ? " is-active" : ""}`}
              onClick={() => setActiveIdx(i)}
            >
              #{ins.index} · {ins.score}
            </button>
          ))}
        </div>
      )}

      {/* Top summary block */}
      <div className="dtop">
        <div className={`dbadge dbadge--${band.tone}`}>
          <span className="dbadge__num">{instance.score}</span>
          <span className="dbadge__chip">{instance.rating}</span>
        </div>
        <div className="dfields">
          <SummaryField label="Duration" value={`${instance.durationSec}s`} />
          <SummaryField label="Qualified" value={instance.qualified ? "Yes" : "No"} />
          <SummaryField
            label="Timestamps"
            value={`${formatTimestamp(instance.timestampStart)} – ${formatTimestamp(instance.timestampEnd)}`}
          />
          <SummaryField
            label="Intent"
            value={<Badge tone={intentTone(instance.intent)}>{instance.intent}</Badge>}
          />
          <SummaryField label="Sale" value={instance.saleMade ? "Yes" : "No"} />
          <SummaryField label="Pitch Intent" value={instance.pitchIntent ? "Yes" : "No"} />
        </div>
      </div>

      <Section label="Recording">
        <AudioPlayer src={instance.recordingUrl} durationSec={instance.recordingDurationSec} />
      </Section>

      <Section label="Summary">
        <p className="dsummary">{instance.summary}</p>
      </Section>

      <Section label="Scores">
        <div className="dscores">
          <ScoreCell label="Clarity" value={instance.scores.clarity} />
          <ScoreCell label="Closing" value={instance.scores.closing} />
          <ScoreCell label="Structure" value={instance.scores.structure} />
          <ScoreCell label="Engagement" value={instance.scores.engagement} />
          <ScoreCell label="USP Delivery" value={instance.scores.uspDelivery} />
          <ScoreCell label="Objection Handling" value={instance.scores.objectionHandling} />
        </div>
        {instance.productsMentionedExtra > 0 && (
          <div className="dscores__pill">
            <Chip tone="green">Products mentioned +{instance.productsMentionedExtra}</Chip>
          </div>
        )}
      </Section>

      <Section label="Signals">
        <div className="dgroups">
          {SIGNAL_GROUPS.map((g) => {
            const items = instance.signals[g.key];
            if (!items.length) return null;
            return (
              <div className="dgroup" key={g.key}>
                <div className="dgroup__label">{g.label}</div>
                <div className="dgroup__chips">
                  {items.map((text, i) => (
                    <Chip key={i} tone={g.tone} block={text.length > 24}>
                      {text}
                    </Chip>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      <Section label="Coaching">
        <div className="dgroups">
          {COACHING_GROUPS.map((g) => {
            const items = instance.coaching[g.key];
            if (!items.length) return null;
            return (
              <div className="dgroup" key={g.key}>
                <div className="dgroup__label">{g.label}</div>
                <div className="dgroup__chips">
                  {items.map((text, i) => (
                    <Chip key={i} tone={g.tone} block>
                      {text}
                    </Chip>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      <div className="ddur-note">
        Recording length {secondsToClock(instance.recordingDurationSec)} · worker {row.worker} · {row.store}
      </div>
    </Drawer>
  );
}
