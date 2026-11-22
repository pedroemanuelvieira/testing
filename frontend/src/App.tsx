import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Empty } from "./components/ui";
import Advisor from "./pages/Advisor";
import Agents from "./pages/Agents";
import DataHub from "./pages/DataHub";
import Glossary from "./pages/Glossary";
import Home from "./pages/Home";
import Models from "./pages/Models";
import ProjectWorkspace from "./pages/ProjectWorkspace";
import Projects from "./pages/Projects";
import UseCases from "./pages/UseCases";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/casos-de-uso" element={<UseCases />} />
        <Route path="/dados" element={<DataHub />} />
        <Route path="/projetos" element={<Projects />} />
        <Route path="/projetos/:id" element={<ProjectWorkspace />} />
        <Route path="/conselheiro" element={<Advisor />} />
        <Route path="/modelos" element={<Models />} />
        <Route path="/agentes" element={<Agents />} />
        <Route path="/glossario" element={<Glossary />} />
        <Route path="/glossario/:termId" element={<Glossary />} />
        <Route path="*" element={<Empty icon="compass" title="Página não encontrada">Use o menu à esquerda para navegar.</Empty>} />
      </Routes>
    </Layout>
  );
}
