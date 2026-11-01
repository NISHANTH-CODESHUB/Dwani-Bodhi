/** School / class / grades / region fields, shared by "Create account" and "Add class". */
import { useEffect, useState } from 'react';
import { hi } from '../i18n/hi';
import { api } from '../lib/api';
import type { RegionOption } from '../lib/types';

export interface ClassValues {
  school_name: string;
  class_name: string;
  grades: number[];
  region_profile: string;
}

export const EMPTY_CLASS: ClassValues = { school_name: '', class_name: '', grades: [], region_profile: 'standard' };

export function classValid(v: ClassValues, withSchool = true): boolean {
  return (!withSchool || !!v.school_name.trim()) && !!v.class_name.trim() && v.grades.length > 0;
}

const GRADES = [1, 2, 3, 4, 5];

let regionCache: RegionOption[] | null = null;

export function ClassFields({
  value,
  onChange,
  withSchool = true,
}: {
  value: ClassValues;
  onChange: (v: ClassValues) => void;
  withSchool?: boolean;
}) {
  const [regions, setRegions] = useState<RegionOption[] | null>(regionCache);
  useEffect(() => {
    if (regionCache) return;
    api.regions().then(
      (r) => {
        regionCache = r;
        setRegions(r);
      },
      () => setRegions([{ id: 'standard', name: 'Standard' }]),
    );
  }, []);
  const set = (patch: Partial<ClassValues>) => onChange({ ...value, ...patch });
  const toggle = (g: number) =>
    set({ grades: value.grades.includes(g) ? value.grades.filter((x) => x !== g) : [...value.grades, g].sort((a, b) => a - b) });

  return (
    <>
      {withSchool && (
        <label className="field">
          <span>{hi.schoolName}</span>
          <input
            value={value.school_name}
            onChange={(e) => set({ school_name: e.target.value })}
            required
            maxLength={200}
            autoComplete="organization"
          />
          <small className="field-hint">{hi.schoolHint}</small>
        </label>
      )}
      <label className="field">
        <span>{hi.className}</span>
        <input value={value.class_name} onChange={(e) => set({ class_name: e.target.value })} required maxLength={120} />
        <small className="field-hint">{hi.classHint}</small>
      </label>
      <fieldset className="field">
        <legend>{hi.grades}</legend>
        <div className="seg" role="group" aria-label={hi.grades}>
          {GRADES.map((g) => (
            <button
              type="button"
              key={g}
              className={`seg-btn ${value.grades.includes(g) ? 'seg-on' : ''}`}
              aria-pressed={value.grades.includes(g)}
              onClick={() => toggle(g)}
            >
              {g}
            </button>
          ))}
        </div>
        <small className="field-hint">{hi.gradesHint}</small>
      </fieldset>
      <label className="field">
        <span>{hi.region}</span>
        <select value={value.region_profile} onChange={(e) => set({ region_profile: e.target.value })} disabled={!regions}>
          {(regions ?? [{ id: value.region_profile, name: hi.loading }]).map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
        <small className="field-hint">{hi.regionHint}</small>
      </label>
    </>
  );
}
