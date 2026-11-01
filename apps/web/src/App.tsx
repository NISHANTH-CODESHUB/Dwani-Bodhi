import { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { Spinner } from './components/common';
import { homePath, useAuth, useClassroom } from './lib/auth';
import { refreshNotifications, startNotificationPolling } from './lib/notifications';
import { startSyncLoop } from './lib/sync';
import { LoginPage } from './teacher/LoginPage';
import { ClassPickPage } from './teacher/ClassPickPage';
import { HomePage } from './teacher/HomePage';

const RosterPage = lazy(() => import('./teacher/RosterPage'));
const ChildEditPage = lazy(() => import('./teacher/ChildEditPage'));
const IdCardsPage = lazy(() => import('./teacher/IdCardsPage'));
const SlatePage = lazy(() => import('./teacher/SlatePage'));
const CardPage = lazy(() => import('./teacher/CardPage'));
const ProfilePage = lazy(() => import('./teacher/ProfilePage'));
const UnsurePage = lazy(() => import('./teacher/UnsurePage'));
const KioskPage = lazy(() => import('./kiosk/KioskPage'));
const ActivityPage = lazy(() => import('./teacher/ActivityPage'));
const AdminDashboardPage = lazy(() => import('./admin/AdminDashboardPage'));
const AdminStudentsPage = lazy(() => import('./admin/AdminStudentsPage'));
const AdminStudentPage = lazy(() => import('./admin/AdminStudentPage'));
const AdminTeachersPage = lazy(() => import('./admin/AdminTeachersPage'));
const HelpPage = lazy(() => import('./teacher/HelpPage'));
const PinPage = lazy(() => import('./teacher/PinPage'));
const AdminPage = lazy(() => import('./admin/AdminPage'));

function RequireAuth() {
  const auth = useAuth();
  useEffect(() => {
    if (!auth) return;
    startSyncLoop();
    startNotificationPolling();
    void refreshNotifications(); // right away after a login or account switch
  }, [auth?.token]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!auth) return <Navigate to="/login" replace />;
  return <Outlet />;
}

function RequireAdmin() {
  const auth = useAuth();
  if (auth && auth.user.role !== 'admin') return <Navigate to={homePath(auth.user.role)} replace />;
  return <Outlet />;
}

function RequireTeacherClass() {
  const auth = useAuth();
  const room = useClassroom();
  if (auth && auth.user.role !== 'teacher') return <Navigate to={homePath(auth.user.role)} replace />;
  if (!room) return <Navigate to="/classes" replace />;
  return <Outlet />;
}

export function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Spinner />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/classes" element={<ClassPickPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="/pin" element={<PinPage />} />
            <Route element={<RequireAdmin />}>
              <Route path="/admin" element={<AdminDashboardPage />} />
              <Route path="/admin/students" element={<AdminStudentsPage />} />
              <Route path="/admin/students/:id" element={<AdminStudentPage />} />
              <Route path="/admin/teachers" element={<AdminTeachersPage />} />
              <Route path="/admin/accounts" element={<AdminPage />} />
            </Route>
            <Route element={<RequireTeacherClass />}>
              <Route path="/" element={<HomePage />} />
              <Route path="/roster" element={<RosterPage />} />
              <Route path="/roster/new" element={<ChildEditPage />} />
              <Route path="/roster/:id" element={<ChildEditPage />} />
              <Route path="/idcards" element={<IdCardsPage />} />
              <Route path="/slate" element={<SlatePage />} />
              <Route path="/card" element={<CardPage />} />
              <Route path="/activity" element={<ActivityPage />} />
              <Route path="/child/:id" element={<ProfilePage />} />
              <Route path="/unsure" element={<UnsurePage />} />
              <Route path="/kiosk/:childId" element={<KioskPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
