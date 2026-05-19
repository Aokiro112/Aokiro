$repos = @(
    "https://github.com/adrianhajdin/project_video_chat",
    "https://github.com/GreatStackDev/gocart",
    "https://github.com/refinedev/refine"
)

foreach ($repo in $repos) {
    $repoName = ($repo -split "/")[-1]
    Write-Host "`n========================================="
    Write-Host "PROCESSING $repoName"
    Write-Host "=========================================`n"
    
    python src/miner/repo_processor.py $repo --skip-install
    python src/miner/global_graph.py $repoName
    python src/miner/dataset_builder.py $repoName --limit 5
}

python src/miner/generate_report.py
