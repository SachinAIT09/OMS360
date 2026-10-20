import React, { lazy } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/charts/styles.css";
import "@mantine/spotlight/styles.css";
import "leaflet/dist/leaflet.css";
import "./app.css";
import { theme } from "./theme";
import { AuthProvider } from "./auth/AuthContext";
import { AppLayout } from "./layout/AppLayout";
import LoginPage from "./pages/LoginPage";
import PublicOutageMap from "./pages/PublicOutageMap";
import { loadProfile } from "./lib/profile";

// Pages load on first visit (smaller first download); the shell shows a loader meanwhile.
const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const EventsPage = lazy(() => import("./pages/EventsPage"));
const EventDetailPage = lazy(() => import("./pages/EventDetailPage"));
const OutagesPage = lazy(() => import("./pages/OutagesPage"));
const RestorationPage = lazy(() => import("./pages/RestorationPage"));
const CrewsPage = lazy(() => import("./pages/CrewsPage"));
const CommsPage = lazy(() => import("./pages/CommsPage"));
const JarvisPage = lazy(() => import("./pages/JarvisPage"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const AssetHealthPage = lazy(() => import("./pages/AssetHealthPage"));
const NetworkExplorerPage = lazy(() => import("./pages/NetworkExplorerPage"));
const AssetDetailPage = lazy(() => import("./pages/AssetDetailPage"));

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } } });

loadProfile().then(() => ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark" forceColorScheme={location.pathname.startsWith("/outage-map") ? "light" : undefined}>
      <Notifications position="bottom-right" limit={4} />
      <QueryClientProvider client={queryClient}>
        <ModalsProvider>
          <BrowserRouter>
            <AuthProvider>
              <Routes>
                <Route path="/outage-map" element={<PublicOutageMap />} />
                <Route path="/login" element={<LoginPage />} />
                <Route element={<AppLayout />}>
                  <Route index element={<OverviewPage />} />
                  <Route path="events" element={<EventsPage />} />
                  <Route path="events/:id" element={<EventDetailPage />} />
                  <Route path="outages" element={<OutagesPage />} />
                  <Route path="restoration" element={<RestorationPage />} />
                  <Route path="crews" element={<CrewsPage />} />
                  <Route path="communications" element={<CommsPage />} />
                  <Route path="jarvis" element={<JarvisPage />} />
                  <Route path="reports" element={<ReportsPage />} />
                  <Route path="asset-health" element={<AssetHealthPage />} />
                  <Route path="network" element={<NetworkExplorerPage />} />
                  <Route path="asset/:id" element={<AssetDetailPage />} />
                  <Route path="admin" element={<AdminPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Route>
              </Routes>
            </AuthProvider>
          </BrowserRouter>
        </ModalsProvider>
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
));
