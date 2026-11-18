import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { StoreProvider } from "./store";
import { Dashboard } from "./pages/Dashboard";
import { ApiList } from "./pages/ApiList";
import { ApiDetail } from "./pages/ApiDetail";
import { TestList } from "./pages/TestList";
import { TestDetail } from "./pages/TestDetail";
import { IssueDetail, IssueList } from "./pages/Issues";

export function App() {
  return (
    <StoreProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="apis" element={<ApiList />} />
            <Route path="apis/:id" element={<ApiDetail />} />
            <Route path="tests" element={<TestList />} />
            <Route path="tests/:id" element={<TestDetail />} />
            <Route path="issues" element={<IssueList />} />
            <Route path="issues/:id" element={<IssueDetail />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </StoreProvider>
  );
}
