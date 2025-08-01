"""
usage: mpirun -n 4 python async_mpi.py 
"""


import asyncio
import time
import random
from mpi4py import MPI

# Initialize MPI
comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()

task_per_worker = 2

async def async_work(task_id, duration):
    """Simulate some asynchronous work"""
    print(f"[Rank {rank}] Starting async task {task_id} (duration: {duration:.2f}s)")
    await asyncio.sleep(duration)
    result = f"Task {task_id} completed by rank {rank}"
    print(f"[Rank {rank}] Finished async task {task_id}")
    return result

async def worker_process():
    print(f"[Rank {rank}] Worker process started")
    tasks = []
    for i in range(task_per_worker):
        task = asyncio.create_task(async_work(f"{rank}-{i}", random.uniform(0.5, 2.0)))
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    
    # Gather results from all processes using MPI
    all_results = comm.gather(results, root=0)
    
    if rank == 0:
        for proc_rank, proc_results in enumerate(all_results):
            print(f"Results from rank {proc_rank}: {proc_results}")
    
    return results

async def coordinator_process():
    """Coordinator process (rank 0) that manages the workflow"""
    print(f"[Rank {rank}] Coordinator process started")
    
    # Send work instructions to all processes
    work_data = {
        'instruction': 'process_data',
        'data': list(range(10 * rank, 10 * (rank + 1)))
    }
    
    work_data = comm.bcast(work_data, root=0)
    
    print(f"[Rank {rank}] Processing data: {work_data['data']}")
    await asyncio.sleep(1.0)  # Simulate async processing
    
    # Simulate collecting status from workers
    status_tasks = []
    for i in range(3):
        task = asyncio.create_task(async_work(f"coord-{i}", 0.3))
        status_tasks.append(task)
    
    coordinator_results = await asyncio.gather(*status_tasks)
    all_results = comm.gather(coordinator_results, root=0)
    
    if rank == 0:
        print("\n=== Coordinator Results ===")
        for proc_rank, proc_results in enumerate(all_results):
            print(f"Coordinator results from rank {proc_rank}: {proc_results}")

async def peer_to_peer_communication():
    """Demonstrate peer-to-peer async communication between processes"""    
    if rank == 0:
        for target_rank in range(1, size):
            message = f"Hello from rank 0 to rank {target_rank}"
            await asyncio.sleep(0.1)  # Simulate send time
            comm.send(message, dest=target_rank, tag=target_rank)
    else:
        # Other ranks receive messages from rank 0
        await asyncio.sleep(0.2)  # Simulate some async work before receiving
        message = comm.recv(source=0, tag=rank)
        print(f"[Rank {rank}] Received: {message}")
        
        # Send acknowledgment back
        ack = f"ACK from rank {rank}"
        comm.send(ack, dest=0, tag=100 + rank)
    
    if rank == 0:
        # Collect acknowledgments
        for source_rank in range(1, size):
            ack = comm.recv(source=source_rank, tag=100 + source_rank)
            print(f"[Rank {rank}] Received acknowledgment: {ack}")

async def main():
    """Main async function that orchestrates the MPI + asyncio workflow"""
    print(f"[Rank {rank}] Starting main function (Process {rank}/{size})")
    
    # Synchronize all processes at the start
    comm.Barrier()
    start_time = time.time()
    try:
        if rank == 0:
            await coordinator_process()
        else:
            # Workers do worker tasks
            await worker_process()
        
        # All processes participate in peer-to-peer communication
        comm.Barrier()  # Synchronize before P2P communication
        await peer_to_peer_communication()
        
        # Final synchronization
        comm.Barrier()
        end_time = time.time()
        
        if rank == 0:
            print(f"\n=== Execution Summary ===")
            print(f"Total execution time: {end_time - start_time:.2f} seconds")
            print(f"Processes used: {size}")
            print("MPI + asyncio integration completed successfully!")
    
    except Exception as e:
        print(f"[Rank {rank}] Error occurred: {e}")
        comm.Abort(1)

if __name__ == "__main__":
    print(f"[Rank {rank}] starting...")
    asyncio.run(main())
    print(f"[Rank {rank}] Process finished.")