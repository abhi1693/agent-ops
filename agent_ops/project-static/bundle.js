const esbuild = require('esbuild');
const { sassPlugin } = require('esbuild-sass-plugin');

const options = {
  outdir: './dist',
  bundle: true,
  minify: false,
  sourcemap: false,
  logLevel: 'error',
};

const args = process.argv.slice(2);

async function bundleScripts() {
  await esbuild.build({
    ...options,
    entryPoints: {
      app: 'src/index.ts',
    },
    target: 'es2018',
  });
  console.log("Bundled 'src/index.ts' to 'dist/app.js'");
}

async function bundleStyles() {
  await esbuild.build({
    ...options,
    sourcemap: false,
    entryPoints: {
      app: 'styles/app.scss',
    },
    plugins: [sassPlugin({ outputStyle: 'expanded' })],
  });
  console.log("Bundled 'styles/app.scss' to 'dist/app.css'");
}

async function main() {
  if (args.includes('--styles')) {
    await bundleStyles();
    return;
  }
  if (args.includes('--scripts')) {
    await bundleScripts();
    return;
  }
  await bundleStyles();
  await bundleScripts();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
