import { useState } from 'react';
import { Notice } from '../components/common';
import { PinChangeForm } from '../components/PinChangeForm';
import { AppShell } from '../components/ui';
import { hi } from '../i18n/hi';
import { getAuth, setAuth } from '../lib/auth';

/** Change PIN at any time. The server ends every other session; this device continues with a fresh token. */
export default function PinPage() {
  const [done, setDone] = useState(false);
  return (
    <AppShell narrow title={hi.pinPageTitle}>
      {done ? (
        <Notice tone="ok">{hi.pinChanged}</Notice>
      ) : (
        <div className="card pin-card">
          <PinChangeForm
            onDone={(res) => {
              const prev = getAuth();
              setAuth({ ...(prev ?? res), token: res.token, user: res.user, classrooms: res.classrooms });
              setDone(true);
            }}
          />
        </div>
      )}
    </AppShell>
  );
}
