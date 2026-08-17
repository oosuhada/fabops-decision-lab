import type {RcaCandidate} from "../../types";

export interface EvidenceRecordPair {
  left: Record<string, unknown>;
  right: Record<string, unknown>;
}

export interface EvidenceRecordDiff {
  shared: EvidenceRecordPair[];
  leftOnly: Array<Record<string, unknown>>;
  rightOnly: Array<Record<string, unknown>>;
}

export interface CandidateEvidenceDiff {
  left: RcaCandidate;
  right: RcaCandidate;
  scoreDelta: number;
  components: Array<{component: string; left: number; right: number; delta: number}>;
  support: EvidenceRecordDiff;
  contradict: EvidenceRecordDiff;
}

function normalizeValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, child]) => [key, normalizeValue(child)]));
  }
  return value;
}

export function stableEvidenceKey(record: Record<string, unknown>) {
  return JSON.stringify(normalizeValue(record));
}

export function diffEvidenceRecords(left: Array<Record<string, unknown>>, right: Array<Record<string, unknown>>): EvidenceRecordDiff {
  const rightBuckets = new Map<string, Array<Record<string, unknown>>>();
  right.forEach((record) => {
    const key = stableEvidenceKey(record);
    const bucket = rightBuckets.get(key) ?? [];
    bucket.push(record);
    rightBuckets.set(key, bucket);
  });

  const shared: EvidenceRecordPair[] = [];
  const leftOnly: Array<Record<string, unknown>> = [];
  left.forEach((record) => {
    const key = stableEvidenceKey(record);
    const bucket = rightBuckets.get(key);
    const matched = bucket?.shift();
    if (matched) shared.push({left: record, right: matched});
    else leftOnly.push(record);
    if (bucket && bucket.length === 0) rightBuckets.delete(key);
  });

  return {
    shared,
    leftOnly,
    rightOnly: Array.from(rightBuckets.values()).flat(),
  };
}

export function buildCandidateEvidenceDiff(left: RcaCandidate, right: RcaCandidate): CandidateEvidenceDiff {
  const componentNames = Array.from(new Set([
    ...Object.keys(left.score_components),
    ...Object.keys(right.score_components),
  ])).sort();

  return {
    left,
    right,
    scoreDelta: left.score - right.score,
    components: componentNames.map((component) => {
      const leftValue = left.score_components[component] ?? 0;
      const rightValue = right.score_components[component] ?? 0;
      return {component, left: leftValue, right: rightValue, delta: leftValue - rightValue};
    }),
    support: diffEvidenceRecords(left.supporting_evidence, right.supporting_evidence),
    contradict: diffEvidenceRecords(left.contradicting_evidence, right.contradicting_evidence),
  };
}
