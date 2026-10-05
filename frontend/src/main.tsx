import React from "react";
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
import OverviewPage from "./pages/OverviewPage";
import EventsPage from "./pages/EventsPage";
import EventDetailPage from "./pages/EventDetailPage";
import OutagesPage from "./pages/OutagesPage";
import RestorationPage from "./pages/RestorationPage";
import CrewsPage from "./pages/CrewsPage";
import CommsPage from "./pages/CommsPage";
import JarvisPage from "./pages/JarvisPage";
import ReportsPage from "./pages/ReportsPage";
import AdminPage from "./pages/AdminPage";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
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
);
