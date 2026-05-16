import test from 'node:test';
import assert from 'node:assert';
import { extractAST } from '../parser.js';

test('Parser successfully extracts React hooks and dependencies', () => {
  const code = `
    import { useEffect, useState } from 'react';
    export const Demo = ({ id }) => {
      const [data, setData] = useState(null);
      useEffect(() => {
        console.log(id);
      }, [id]);
      return <div>{data}</div>;
    }
  `;
  const ast = extractAST(code, 'Demo.tsx');
  
  assert.deepStrictEqual(ast.exports.includes('Demo'), true);
  assert.deepStrictEqual(ast.imports.includes('react'), true);
  assert.deepStrictEqual(ast.hooks.includes('useEffect'), true);
  assert.deepStrictEqual(ast.hooks.includes('useState'), true);
  assert.deepStrictEqual(ast.deps['useEffect'].includes('id'), true);
});

test('Parser successfully extracts complex JSX components', () => {
  const code = `
    import { Header } from './Header';
    import { Footer } from './Footer';
    export default function App() {
      return (
        <Layout.Main>
          <Header />
          <Footer />
        </Layout.Main>
      );
    }
  `;
  const ast = extractAST(code, 'App.tsx');
  
  assert.deepStrictEqual(ast.exports.includes('App'), true);
  assert.deepStrictEqual(ast.children.includes('Header'), true);
  assert.deepStrictEqual(ast.children.includes('Footer'), true);
  assert.deepStrictEqual(ast.children.includes('Layout.Main'), true);
});
