import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "../../lib/api";
import { loadGooglePlaces, isPlacesAvailable } from "../../lib/googlePlaces";
import { ROLE_CAN_EDIT, ManagementCard, InlineField, EditInput } from "./driverCCUtils";
import EvidenceActions from "./EvidenceActions";

/**
 * EB-R03B-II-FIX · Render the ACTUAL current Profile Photo thumbnail via
 * the authenticated `/api/documents/{id}/preview` endpoint. No storage_key
 * is ever exposed to the browser; the image is retrieved as a blob and
 * rendered from an object URL that is revoked on unmount or replacement.
 */
function ProfilePhotoThumb({ documentId }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    let obj = null;
    setFailed(false);
    setUrl(null);
    if (!documentId) return () => {};
    (async () => {
      try {
        const res = await api.get(`/documents/${documentId}/preview`, { responseType: "blob" });
        if (cancelled) return;
        obj = URL.createObjectURL(res.data);
        setUrl(obj);
      } catch (_e) {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      if (obj) URL.revokeObjectURL(obj);
    };
  }, [documentId]);

  if (!documentId || failed) {
    return (
      <div
        data-testid="dcc-profile-photo-fallback"
        className="w-14 h-14 rounded-md bg-slate-100 border border-slate-200 flex items-center justify-center text-[9px] text-slate-500 uppercase tracking-widest"
      >
        Photo
      </div>
    );
  }
  if (!url) {
    return (
      <div
        data-testid="dcc-profile-photo-loading"
        className="w-14 h-14 rounded-md bg-slate-100 border border-slate-200 animate-pulse"
      />
    );
  }
  return (
    <img
      src={url}
      alt="Driver profile"
      data-testid="dcc-profile-photo-img"
      className="w-14 h-14 rounded-md object-cover border border-slate-200 bg-slate-100"
      onError={() => setFailed(true)}
    />
  );
}
/**
 * FA-03 · Residential-address input with Google Places autocomplete.
 * Falls back to a plain text input when the key is missing or the API
 * fails to load. Only ``place.formatted_address`` is persisted — no
 * place_id, no coordinates, no raw Places response.
 */
function AddressAutocompleteInput({ value, onChange, testid }) {
  const inputRef = useRef(null);
  const acRef = useRef(null);
  const [available, setAvailable] = useState(isPlacesAvailable());
  const [attempted, setAttempted] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const places = await loadGooglePlaces();
      if (cancelled) return;
      setAttempted(true);
      if (!places || !inputRef.current) { setAvailable(false); return; }
      try {
        acRef.current = new places.Autocomplete(inputRef.current, {
          types: ["address"],
          componentRestrictions: { country: ["au"] },
          fields: ["formatted_address"],
        });
        acRef.current.addListener("place_changed", () => {
          const p = acRef.current?.getPlace();
          const formatted = p?.formatted_address;
          if (formatted) onChange(formatted);
        });
        setAvailable(true);
      } catch { setAvailable(false); }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="grid grid-cols-3 gap-2 items-start text-xs" data-testid="edit-residential-address-row">
      <label htmlFor="edit-residential-address" className="col-span-1 text-slate-500 pt-1.5">
        Residential Address
      </label>
      <div className="col-span-2">
        <input
          id="edit-residential-address"
          ref={inputRef}
          type="text"
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border border-slate-200 rounded px-2 py-1 text-xs focus:outline-cyan-500"
          data-testid={testid}
          autoComplete="off"
        />
        {attempted && !available && (
          <div className="text-[10px] text-slate-400 mt-0.5"
               data-testid="address-autocomplete-unavailable">
            Address suggestions unavailable
          </div>
        )}
      </div>
    </div>
  );
}



export default function DriverDetailsCard({ data, role, onSaved }) {
  const d = data.driver || {};
  const photo = data.documents?.profile_photo || null;
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const initial = useRef({});
  const canEdit = ROLE_CAN_EDIT.has(role);

  const startEdit = () => {
    const f = {
      residential_address: d.residential_address || "",
      mobile_number: d.mobile_number || "",
      email: d.email || "",
      emergency_contact_name: d.emergency_contact_name || "",
      emergency_contact_phone: d.emergency_contact_phone || "",
    };
    initial.current = f;
    setForm(f);
    setEditing(true);
  };
  const dirty = editing && JSON.stringify(form) !== JSON.stringify(initial.current);

  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/drivers/${d.id}`, form);
      toast.success("Driver details saved");
      setEditing(false);
      await onSaved?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <ManagementCard
      testid="card-driver-details"
      section="driver-details"
      title="Driver Details"
      subtitle="Canonical identity + contact"
      canEdit={canEdit}
      editing={editing}
      saving={saving}
      dirty={dirty}
      onEditToggle={startEdit}
      onCancel={() => setEditing(false)}
      onSave={save}
    >
      {editing ? (
        <>
          <AddressAutocompleteInput value={form.residential_address} onChange={(v) => setForm({ ...form, residential_address: v })} testid="edit-residential-address" />
          <EditInput label="Mobile Number" value={form.mobile_number} onChange={(v) => setForm({ ...form, mobile_number: v })} testid="edit-mobile-number" />
          <EditInput label="Email" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} testid="edit-email" />
          <EditInput label="Emergency Name" value={form.emergency_contact_name} onChange={(v) => setForm({ ...form, emergency_contact_name: v })} testid="edit-emergency-name" />
          <EditInput label="Emergency Phone" value={form.emergency_contact_phone} onChange={(v) => setForm({ ...form, emergency_contact_phone: v })} testid="edit-emergency-phone" />
        </>
      ) : (
        <>
          <div className="flex items-start gap-3 pb-2 border-b border-slate-100 mb-2" data-testid="dcc-profile-photo-row">
            {photo?.id ? (
              <ProfilePhotoThumb documentId={photo.id} />
            ) : (
              <div
                data-testid="dcc-profile-photo-empty"
                className="w-14 h-14 rounded-md bg-slate-50 border border-dashed border-slate-300 flex items-center justify-center text-[9px] text-slate-400 uppercase tracking-widest"
              >
                No Photo
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500 font-semibold">
                Profile Photo
              </div>
              <div className="text-[11px] text-slate-500 truncate">
                {photo?.title || "Upload the driver's current profile photo"}
              </div>
              <EvidenceActions
                evidenceDoc={photo}
                canEdit={canEdit}
                acceptHint="image/*"
                uploadPayload={{
                  title: `Profile Photo — ${d.full_name || d.id}`,
                  document_type: "Profile Photo",
                  entity_type: "Driver",
                  entity_id: d.id,
                  relationship_type: "Evidence",
                  is_primary: "true",
                  sensitivity: "Standard",
                }}
                onChanged={onSaved}
                testidPrefix="dcc-photo"
              />
            </div>
          </div>
          <InlineField label="Address" value={d.residential_address} testid="field-residential-address" />
          <InlineField label="Mobile" value={d.mobile_number ? <a href={`tel:${d.mobile_number}`} className="text-cyan-700 hover:underline">{d.mobile_number}</a> : null} testid="field-mobile" />
          <InlineField label="Email" value={d.email ? <a href={`mailto:${d.email}`} className="text-cyan-700 hover:underline">{d.email}</a> : null} testid="field-email" />
          <InlineField label="Emergency" value={d.emergency_contact_name || null} testid="field-emergency-name" />
          <InlineField label="Emerg. Phone" value={d.emergency_contact_phone || null} testid="field-emergency-phone" />
        </>
      )}
    </ManagementCard>
  );
}
